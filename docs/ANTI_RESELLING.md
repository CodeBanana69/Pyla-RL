# Anti-Reselling Policy

Pyla-RL is **free**, **open source**, and licensed under [Creative Commons Attribution-NonCommercial 4.0 International](../LICENSE) (CC BY-NC 4.0).

## Official free downloads

Download Pyla-RL only from these official channels:

- **GitHub:** https://github.com/CodeBanana69/Pyla-RL
- **Pyla Discord:** https://discord.gg/xUusk3fw4A (community link; also used for support and reseller reports)

If someone asks you to pay for Pyla-RL, a "premium build," or a repackaged zip, that is **not** an official copy.

## What is prohibited

- Selling or reselling Pyla-RL (or repackaged copies) for money
- Charging for downloads, "VIP access," or paid setup that includes Pyla-RL as the product
- Removing the LICENSE file or hiding that the software is free and open source
- Claiming exclusive or official ownership without permission

## What is allowed

- Personal use for free
- Modifying the source code for non-commercial use
- Sharing the source with attribution
- Non-commercial forks that keep the license and credit the project

Optional [Patreon support](https://www.patreon.com/pyla/membership) helps development. It is **not** required to use the bot and is **not** a purchase license.

## Report a reseller

1. Open a [reseller report issue](https://github.com/CodeBanana69/Pyla-RL/issues/new?template=reseller-report.yml) on GitHub, or
2. Post in the Pyla Discord with the seller link, price, and screenshots if possible.

Include:

- URL or platform where it is being sold
- Price asked
- Date you found it
- Screenshots (if available)

## For developers

Contributors may set `PYLA_RL_DEV=1` to skip unofficial-source warnings on local forks. Do not distribute builds with this flag to end users.

Generate release metadata before publishing:

```bash
python tools/write_build_info.py
```
