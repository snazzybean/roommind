# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      107 |       83 |     22% |32-34, 40-61, 66-67, 73-111, 116-125, 130-153, 158-196 |
| custom\_components/roommind/binary\_sensor.py                      |       37 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |       87 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |       99 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      191 |        1 |     99% |        58 |
| custom\_components/roommind/control/mpc\_controller.py             |      793 |       50 |     94% |385-387, 405-406, 440-443, 454-461, 474-475, 520, 814-816, 984, 1048-1060, 1144-1145, 1151, 1232-1243, 1303-1304, 1404-1405, 1437-1438, 1535, 1537, 1551, 1556, 1561 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      166 |       10 |     94% |82, 115, 285, 290, 295, 303, 309, 312-315 |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        2 |     98% |    72, 91 |
| custom\_components/roommind/control/thermal\_model.py              |      423 |       18 |     96% |396, 670, 861-876, 935, 1058, 1065-1069 |
| custom\_components/roommind/coordinator.py                         |      791 |       53 |     93% |306-307, 499-502, 538, 677-678, 688, 690, 1020, 1061, 1119, 1337-1340, 1474-1476, 1480-1486, 1490, 1495, 1510, 1515, 1517, 1529, 1534-1539, 1543, 1576, 1578, 1581, 1584, 1588, 1600-1601, 1712, 1732-1740, 1758-1759, 1774-1779, 1796-1797 |
| custom\_components/roommind/diagnostics.py                         |      164 |       11 |     93% |82, 120, 187-188, 217-223 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      157 |        2 |     99% |  121, 184 |
| custom\_components/roommind/managers/cover\_manager.py             |      123 |        1 |     99% |       195 |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      143 |        2 |     99% |   74, 201 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       54 |        1 |     98% |        28 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      122 |        4 |     97% |60, 68, 199, 205 |
| custom\_components/roommind/managers/mold\_manager.py              |       69 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/valve\_manager.py             |      108 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       54 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       31 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |       54 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      158 |       10 |     94% |44-47, 295-297, 323-326 |
| custom\_components/roommind/store.py                               |      145 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |       93 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      101 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      129 |        1 |     99% |       110 |
| custom\_components/roommind/utils/mold\_utils.py                   |       32 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       22 |        0 |    100% |           |
| custom\_components/roommind/utils/schedule\_utils.py               |      149 |        7 |     95% |139-140, 145-146, 154-155, 224 |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      263 |        2 |     99% |   614-619 |
| **TOTAL**                                                          | **5139** |  **270** | **95%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/snazzybean/roommind/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/snazzybean/roommind/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fsnazzybean%2Froommind%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.