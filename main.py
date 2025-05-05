import requests
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime
import ipaddress
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


@dataclass
class SubnetInfo:
    subnet: str
    latency: float
    method: str
    reachable: bool
    test_ip: str


@dataclass
class EndpointData:
    location: str
    subnets: List[SubnetInfo]
    timestamp: datetime


@dataclass
class DCAssignment:
    primary_dc: str
    possible_dcs: Set[str]
    latencies: Dict[str, float]
    confidence: str  # "high", "medium", "low", "unknown"


def get_headers() -> Dict[str, str]:
    """获取带有 Cloudflare Access 认证信息的请求头"""
    cf_id = os.getenv("cfid")
    cf_secret = os.getenv("cfsecret")

    if not cf_id or not cf_secret:
        raise ValueError(
            "Cloudflare Access credentials not found in environment variables"
        )

    return {"CF-Access-Client-Id": cf_id, "CF-Access-Client-Secret": cf_secret}


def fetch_endpoint_data(url: str) -> Optional[EndpointData]:
    try:
        headers = get_headers()
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if data["status"] != "ok":
            return None

        subnets = []
        for subnet_data in data["data"]["subnets"]:
            subnet = SubnetInfo(
                subnet=subnet_data["subnet"],
                latency=subnet_data["latency"],
                method=subnet_data["method"],
                reachable=subnet_data["reachable"],
                test_ip=subnet_data["test_ip"],
            )
            subnets.append(subnet)

        return EndpointData(
            location=data["location"],
            subnets=subnets,
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )
    except Exception as e:
        print(f"Error fetching data from {url}: {e}")
        return None


def determine_dc_location(
    subnet: str, endpoint_data: List[EndpointData]
) -> DCAssignment:
    # 已知的DC位置映射
    dc_locations = {"SG": "Singapore", "US": "Miami", "EU": "Amsterdam"}

    # 获取该subnet在所有端点的延迟
    latencies = {}
    for data in endpoint_data:
        for subnet_info in data.subnets:
            if subnet_info.subnet == subnet:
                latencies[data.location] = subnet_info.latency
                break

    if not latencies:
        return DCAssignment(
            primary_dc="Undefined",
            possible_dcs=set(),
            latencies={},
            confidence="unknown",
        )

    # 检查有多少个端点的延迟小于20ms
    low_latency_dcs = {dc_locations[loc] for loc, lat in latencies.items() if lat <= 20}

    # 如果所有延迟都大于20ms，归类为Undefined
    if not low_latency_dcs:
        return DCAssignment(
            primary_dc="Undefined",
            possible_dcs=set(),
            latencies={dc_locations[loc]: lat for loc, lat in latencies.items()},
            confidence="unknown",
        )

    # 如果有多个延迟小于20ms的端点，归类为Undefined
    if len(low_latency_dcs) > 1:
        return DCAssignment(
            primary_dc="Undefined",
            possible_dcs=low_latency_dcs,
            latencies={dc_locations[loc]: lat for loc, lat in latencies.items()},
            confidence="unknown",
        )

    # 如果只有一个延迟小于20ms的端点，使用该端点作为主要DC
    min_latency_location = min(latencies.items(), key=lambda x: x[1])[0]
    return DCAssignment(
        primary_dc=dc_locations[min_latency_location],
        possible_dcs={dc_locations[min_latency_location]},
        latencies={dc_locations[loc]: lat for loc, lat in latencies.items()},
        confidence="high",
    )


def generate_config_files(dc_groups: Dict[str, List[Dict]]) -> None:
    """生成各个DC的配置文件"""
    # DC名称到配置文件的映射
    dc_file_map = {
        "Singapore": "telegramSG.conf",
        "Miami": "telegramUS.conf",
        "Amsterdam": "telegramEU.conf",
    }

    # 为每个DC生成配置文件
    for dc_name, file_name in dc_file_map.items():
        if dc_name in dc_groups:
            with open(file_name, "w") as f:
                for subnet_info in dc_groups[dc_name]:
                    f.write(f"IP-CIDR,{subnet_info['subnet']},no-resolve\n")
            print(f"Generated {file_name}")


def main():
    endpoints = [
        "https://tg-finder-eu.otherdc.com/latency",
        "https://tg-finder-sg.otherdc.com/latency",
        "https://tg-finder-us.otherdc.com/latency",
    ]

    # 获取所有端点的数据
    endpoint_data = []
    for url in endpoints:
        data = fetch_endpoint_data(url)
        if data:
            endpoint_data.append(data)

    if not endpoint_data:
        print("Failed to fetch data from any endpoint")
        return

    # 收集所有唯一的subnet
    all_subnets = set()
    for data in endpoint_data:
        for subnet_info in data.subnets:
            all_subnets.add(subnet_info.subnet)

    # 分析每个subnet的DC位置
    results = {}
    for subnet in sorted(all_subnets):
        dc_assignment = determine_dc_location(subnet, endpoint_data)
        results[subnet] = dc_assignment

    # 按DC位置分组
    dc_groups = {"Singapore": [], "Miami": [], "Amsterdam": [], "Undefined": []}

    # 组织结果
    for subnet, assignment in results.items():
        if assignment.primary_dc == "Undefined":
            dc_groups["Undefined"].append(
                {
                    "subnet": subnet,
                    "latencies": assignment.latencies,
                    "possible_dcs": (
                        list(assignment.possible_dcs)
                        if assignment.possible_dcs
                        else None
                    ),
                }
            )
        else:
            dc_groups[assignment.primary_dc].append(
                {
                    "subnet": subnet,
                    "latencies": assignment.latencies,
                    "confidence": assignment.confidence,
                }
            )

    # 创建输出结果
    output = {
        "dc_assignments": dc_groups,
        "summary": {
            "total_subnets": len(all_subnets),
            "assigned_subnets": len(all_subnets) - len(dc_groups["Undefined"]),
            "undefined_subnets": len(dc_groups["Undefined"]),
            "confidence_levels": {
                "high": sum(
                    1 for subnet in results.values() if subnet.confidence == "high"
                ),
                "unknown": sum(
                    1 for subnet in results.values() if subnet.confidence == "unknown"
                ),
            },
        },
    }

    # 保存结果到JSON文件
    with open("dc_assignments.json", "w") as f:
        json.dump(output, f, indent=2)

    # 生成配置文件
    generate_config_files(dc_groups)

    # 打印摘要信息
    print("\nDC Assignment Summary:")
    print("=====================")
    print(f"Total subnets analyzed: {output['summary']['total_subnets']}")
    print(f"Successfully assigned: {output['summary']['assigned_subnets']}")
    print(f"Undefined assignments: {output['summary']['undefined_subnets']}")
    print("\nConfidence Levels:")
    print(f"High confidence: {output['summary']['confidence_levels']['high']}")
    print(f"Unknown: {output['summary']['confidence_levels']['unknown']}")
    print("\nDetailed results have been saved to dc_assignments.json")
    print("Configuration files have been generated for each DC")


if __name__ == "__main__":
    main()
