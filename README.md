# Telegram DC Configuration Generator

This repository automatically generates Telegram DC (Data Center) configuration files based on latency measurements from three different locations.

## Features

- Automatically measures latency to Telegram IP ranges from three locations:
  - Singapore
  - Miami (US)
  - Amsterdam (EU)
- Generates configuration files for each DC
- Runs weekly to keep configurations up to date
- Creates GitHub releases with the generated files

## Generated Files

- `telegramSG.conf`: IP ranges for Singapore DC
- `telegramUS.conf`: IP ranges for Miami DC
- `telegramEU.conf`: IP ranges for Amsterdam DC
- `dc_assignments.json`: Detailed analysis of IP assignments

## Usage

### Automatic Updates

The configuration files are automatically generated every Friday at 6:00 AM (UTC+8) and published as a GitHub release.

### Manual Generation

You can also manually trigger the generation by:

1. Going to the "Actions" tab
2. Selecting "Generate Telegram DC Configs"
3. Clicking "Run workflow"

### Using the Generated Files

The generated `.conf` files can be used with various proxy tools. Each line follows the format:

```
IP-CIDR,<subnet>,no-resolve
```

## Setup

To run this locally:

1. Clone the repository
2. Create a `.env` file with your Cloudflare Access credentials:
   ```
   cfid=your_client_id_here
   cfsecret=your_client_secret_here
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the generator:
   ```bash
   python main.py
   ```

## GitHub Secrets

The following secrets need to be set in your GitHub repository:

- `CF_ACCESS_CLIENT_ID`: Your Cloudflare Access client ID
- `CF_ACCESS_CLIENT_SECRET`: Your Cloudflare Access client secret

## License

MIT License
