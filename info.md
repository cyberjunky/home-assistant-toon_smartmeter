[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/custom-components/hacs)  [![made-with-python](https://img.shields.io/badge/Made%20with-Python-1f425f.svg)](https://www.python.org/) [![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.me/cyberjunkynl/)

## TOON Smart Meter Sensor Component
This is a Custom Component for Home-Assistant (https://home-assistant.io) reads and displays sensor values from the meteradapter connected to a rooted TOON thermostat.

NOTE: This component only works with rooted TOON devices.
TOON thermostats are available in The Netherlands and Belgium.

More information about rooting your TOON can be found here:
[Eneco TOON as Domotica controller](http://www.domoticaforum.eu/viewforum.php?f=87)

## Usage
To use this component in your installation, add the following to your `configuration.yaml` file:

```yaml
# Example configuration.yaml entry

sensor:
  - platform: toon_smartmeter
    host: IP_ADDRESS
    port: 10080
    scan_interval: 10
    resources:
      - gasused
      - gasusedcnt
      - elecusageflowpulse
      - elecusagecntpulse
      - elecusageflowlow
      - elecusagecntlow
      - elecusageflowhigh
      - elecusagecnthigh
      - elecprodflowlow
      - elecprodcntlow
      - elecprodflowhigh
      - elecprodcnthigh
      - elecsolar
      - elecsolarcnt
      - heat
```

Configuration variables:

- **host** (*Required*): The IP address on which the TOON can be reached.
- **port** (*Optional*): Port used by your TOON. (default = 10080)
- **scan_interval** (*Optional*): Number of seconds between polls. (default = 10)
- **resources** (*Required*): This section tells the component which values to display, you can leave out the elecprod values if your don't generate power and the elecusage*pulse types if you use the P1 connection.

![alt text](https://github.com/cyberjunky/home-assistant-toon_smartmeter/blob/master/screenshots/toon-smartmeter-badges.png?raw=true "TOON Smart Meter Badges")

If you want them grouped instead of having the separate sensor badges, you can use this in your `groups.yaml`:

```yaml
# Example groups.yaml entry

Smart Meter:
  - sensor.toon_gas_used_last_hour
  - sensor.toon_gas_used_cnt
  - sensor.toon_power_use_cnt
  - sensor.toon_power_use
  - sensor.toon_p1_power_prod_low
  - sensor.toon_p1_power_prod_high
  - sensor.toon_p1_power_prod_cnt_low
  - sensor.toon_p1_power_prod_cnt_high
  - sensor.toon_p1_power_use_cnt_pulse
  - sensor.toon_p1_power_use_cnt_low
  - sensor.toon_p1_power_use_cnt_high
  - sensor.toon_p1_power_use_low
  - sensor.toon_p1_power_use_high
  - sensor.toon_p1_power_solar
  - sensor.toon_p1_power_solar_cnt
  - sensor.toon_p1_heat
```

## Screenshots

![alt text](https://github.com/cyberjunky/home-assistant-toon_smartmeter/blob/master/screenshots/toon-smartmeter.png?raw=true "Screenshot TOON Smart Meter")
![alt text](https://github.com/cyberjunky/home-assistant-toon_smartmeter/blob/master/screenshots/toon-smartmeter-graph-gasused.png?raw=true "Screenshot TOON Graph Gas Used")
![alt text](https://github.com/cyberjunky/home-assistant-toon_smartmeter/blob/master/screenshots/toon-smartmeter-graph-poweruselow.png?raw=true "Screenshot TOON Graph Power Use Low")

## Donation
[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.me/cyberjunkynl/)
