# snmp
[![debian12-epics](https://github.com/jeonghanlee/snmp/actions/workflows/debian12.yml/badge.svg)](https://github.com/jeonghanlee/snmp/actions/workflows/debian12.yml)
[![rocky9-epics](https://github.com/jeonghanlee/snmp/actions/workflows/rocky9.yml/badge.svg)](https://github.com/jeonghanlee/snmp/actions/workflows/rocky9.yml)

Privately customization version with several patches of the NSCL/FRIB SNMP driver [1] with 1.1.0.4 version. 

## Requirements

* Packages: https://github.com/jeonghanlee/pkg_automation
* Generic MIB files
  * Debian: aptitude install snmp-mibs-downloader
  * Rocky: https://github.com/jeonghanlee/snmp-mibs-downloader-env

## Request-driven inputs

`SnmpRequest` provides opt-in asynchronous reads for `ai`, `longin`, and
`stringin`. Existing `Snmp` records retain their polling behavior.
See [configuration and completion semantics](docs/snmp-request.md) and
[real IOC tests](tests/README.md).
 
## Update

* Download epics-snmp-1.1.0.3.zip from https://groups.nscl.msu.edu/controls/
* Unzip it into git clone repo
* Do dos2unix
* git diff

### Practical commands
Commands
```bash
bash scripts/clean_frib.sh
```
Then, most changes are in `devsnmp.cpp`

## Reference 
[1] https://groups.nscl.msu.edu/controls/files/devSnmp.html
