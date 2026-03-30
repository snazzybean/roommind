# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      107 |       83 |     22% |32-34, 40-61, 66-67, 73-111, 116-125, 130-153, 158-196 |
| custom\_components/roommind/binary\_sensor.py                      |       37 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |       87 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |       97 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      191 |        1 |     99% |        58 |
| custom\_components/roommind/control/mpc\_controller.py             |      762 |       52 |     93% |153-154, 298-300, 318-319, 353-356, 367-374, 387-388, 433, 727-729, 897, 961-973, 1057-1058, 1064, 1145-1156, 1216-1217, 1317-1318, 1350-1351, 1448, 1450, 1464, 1469, 1474 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      166 |       10 |     94% |82, 115, 285, 290, 295, 303, 309, 312-315 |
| custom\_components/roommind/control/residual\_heat.py              |       24 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       54 |        1 |     98% |        70 |
| custom\_components/roommind/control/thermal\_model.py              |      421 |       17 |     96% |396, 670, 861-876, 1054, 1061-1065 |
| custom\_components/roommind/coordinator.py                         |      706 |       31 |     96% |305-306, 466-469, 505, 639-640, 650, 652, 872, 913, 971, 1175-1178, 1324, 1326, 1338, 1343-1348, 1352, 1438-1446, 1454, 1478-1479, 1497-1498 |
| custom\_components/roommind/diagnostics.py                         |      161 |       11 |     93% |80, 118, 184-185, 214-220 |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      147 |        2 |     99% |  119, 171 |
| custom\_components/roommind/managers/cover\_manager.py             |      116 |        1 |     99% |       181 |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      118 |        2 |     98% |   184-185 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       52 |        0 |    100% |           |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      122 |        4 |     97% |60, 68, 199, 205 |
| custom\_components/roommind/managers/mold\_manager.py              |       69 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       38 |        0 |    100% |           |
| custom\_components/roommind/managers/valve\_manager.py             |      100 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       54 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       31 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |       54 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      158 |       10 |     94% |44-47, 295-297, 323-326 |
| custom\_components/roommind/store.py                               |      138 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |       93 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      101 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      129 |        1 |     99% |       110 |
| custom\_components/roommind/utils/mold\_utils.py                   |       32 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       22 |        0 |    100% |           |
| custom\_components/roommind/utils/schedule\_utils.py               |      154 |        7 |     95% |138-139, 144-145, 153-154, 223 |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      263 |        2 |     99% |   614-619 |
| **TOTAL**                                                          | **4935** |  **247** | **95%** |           |


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