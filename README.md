snmp
===
Privately customization version of the NSCL/FRIB SNMP driver [1] with 1.0.0.2 version. 


## Requirements

* Packages : https://github.com/jeonghanlee/pkg_automation
* Generic MIB files
  * Debian : aptitude install snmp-mibs-downloader
  * CentOS : https://github.com/jeonghanlee/centos-mib-downloader
 
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
