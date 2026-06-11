# Brawl Stars API

## Setup

1. Create a developer account at https://developer.brawlstars.com/
2. Open the **API** tab or `cfg/brawl_stars_api.toml`.
3. Fill in:
   - `player_tag`
   - `developer_email`
   - `developer_password`

## What it enables

- **Trophy autofill** when picking brawlers
- **Push All / Build Queue** on the Farm Plan tab
- Auto key refresh for your current public IP

## Safety

- Keep `delete_all_tokens = false` unless you intend to delete every key on your account.
- Do not commit filled credentials to GitHub.

## Push All flow

1. Configure API credentials.
2. Open Brawl Stars on the emulator lobby.
3. On **Farm Plan**, set a trophy target and click **Build Queue**.

Only brawlers below the target (from API data) are added.
