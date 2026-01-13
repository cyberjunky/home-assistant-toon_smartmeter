[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)  [![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/) [![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.me/cyberjunkynl/)

# Toon Smart Meter Custom Integration

A Home Assistant custom integration that reads and displays sensor values from the meter adapter connected to a rooted Toon thermostat. Get real-time insights into gas usage, electricity consumption, solar production, and more.

> **Note:** This integration only works with **rooted Toon devices**.
> Toon thermostats are available in The Netherlands and Belgium (as Boxx).

More information about rooting your Toon can be found here:
[Eneco Toon as Domotica controller](http://www.domoticaforum.eu/viewforum.php?f=87)

## Supported Features

Monitor your smart meter with these sensors:

- **Gas Used Last Hour** - Current gas flow
- **Gas Used Total** - Total gas consumption
- **Power Use** - Current electricity usage (pulse)
- **P1 Power Use Low/High** - Electricity usage by tariff
- **P1 Power Prod Low/High** - Electricity production by tariff
- **Energy counters** - Total consumption/production by tariff
- **Solar Power/Energy** - Solar production (if available)
- **Heat** - District heating (if available)
- **Water Flow/Quantity** - Water usage (if available)

All sensors are created automatically and grouped under a single device. Disable sensors you don't need via entity settings.

## Screenshots

![Toon Smart Meter](https://github.com/cyberjunky/home-assistant-toon_smartmeter/blob/master/screenshots/toon-smartmeter.png?raw=true)

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=cyberjunky&repository=home-assistant-toon_smartmeter&category=integration)

Alternatively:

1. Install [HACS](https://hacs.xyz) if not already installed
2. Search for "Toon Smart Meter" in HACS
3. Click **Download**
4. Restart Home Assistant
5. Add via Settings → Devices & Services

### Manual Installation

1. Copy the `custom_components/toon_smartmeter` folder to your `<config>/custom_components/` directory
2. Restart Home Assistant
3. Add via Settings → Devices & Services

## Configuration

### Adding the Integration

1. Navigate to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **"Toon Smart Meter"**
4. Enter your configuration:
   - **Host**: Your Toon's IP address
   - **Port**: Default is `80`
   - **Name**: Friendly name prefix (default: "Toon")
   - **Update Interval**: Seconds between updates (default: `10`)

The integration validates your connection and creates all sensors automatically.

### Migrating from YAML

> **Note:** YAML configuration is deprecated as of v2.0.0

If you previously configured this integration in `configuration.yaml`, your settings will be **automatically imported** on your first restart after updating.

**Your old YAML config** (will be migrated):

```yaml
sensor:
  - platform: toon_smartmeter
    host: 192.168.1.100
    port: 80
    scan_interval: 10
    resources:
      - gasused
      - gasusedcnt
      ...
```

**After migration:**

1. Remove the YAML configuration from `configuration.yaml`
2. Manage all settings via **Settings** → **Devices & Services** → **Toon Smart Meter** → **Configure**
3. Disable unwanted sensors through entity settings

### Modifying Settings

Change integration settings without restarting Home Assistant:

1. Go to **Settings** → **Devices & Services**
2. Find **Toon Smart Meter**
3. Click **Configure** icon
4. Modify name or scan interval
5. Click **Submit**

## Energy Dashboard

You can configure your Energy Dashboard like so:

![Energy Dashboard](https://github.com/cyberjunky/home-assistant-toon_smartmeter/blob/master/screenshots/dashboard.png?raw=true)

## Advanced Usage

### Get Total Power Usage (Both Tariffs)

```yaml
template:
  - sensor:
    - unit_of_measurement: W
      name: Total Power Usage
      icon: mdi:lightning-bolt
      state: "{{ states('sensor.toon_smart_meter_p1_power_use_low') | int + states('sensor.toon_smart_meter_p1_power_use_high') | int }}"
```

### Calculate Gas Used Today

```yaml
utility_meter:
  gas_used_today:
    name: "Gas Used Today"
    source: sensor.toon_smart_meter_gas_used_total
    cycle: daily
```

## Troubleshooting

### Enable Debug Logging

Add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.toon_smartmeter: debug
```

### Common Issues

| Issue | Solution |
|-------|----------|
| Cannot connect | Verify IP address and ensure Toon is rooted and accessible |
| Sensors unavailable | Some sensors only appear if the corresponding meter is connected |
| Missing gas/water sensors | These require specific meter adapters connected to the Toon |

## Donation

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.me/cyberjunkynl/)

## License

MIT License - see [LICENSE](LICENSE) file for details.
