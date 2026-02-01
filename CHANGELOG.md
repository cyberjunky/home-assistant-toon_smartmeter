# Changelog

## 2.0.1

### New Features

- **Z-Wave Power Plugs** - Auto-detection of paired Z-Wave plugs (e.g., Fibaro Wall Plugs) with switch control, power (W), and energy (kWh) sensors

## 2.0.0

### Breaking Changes

- Migrated to Config Flow UI - YAML configuration is deprecated but will be auto-imported
- All sensors are now created by default (disable unwanted sensors via entity settings)

### New Features

- Added total electricity usage sensor (P1 Power Use) - combines high and low tariffs
- Added total electricity production sensor (P1 Power Prod) - combines high and low tariffs  
- Added total counters for usage and production (P1 Power Use Cnt, P1 Power Prod Cnt)
- Automatic device discovery - detects available meters without manual configuration
- All sensors grouped under a single device for easier management
- Reconfigure integration settings without restart

### Fixes

- Fixed HAE_METER_v2 device detection - production meters (v2_4, v2_6) now correctly identified
- Fixed HAE_METER_v3 device detection - swapped v3_5/v3_6 to match actual meter types
- Fixed gas sensor state_class warning for "Gas Used Last Hour" sensor
- Added support for `elec_solar` semantic type for solar detection
- Improved detection of all meter versions (v2, v3, v4)

### Technical

- Complete rewrite using DataUpdateCoordinator pattern
- Async-first architecture for better performance
- Proper entity unique IDs for entity registry
- Translation support via strings.json

