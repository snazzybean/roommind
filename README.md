# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      150 |       90 |     40% |41-43, 49-76, 99-100, 106-144, 149-160, 176-199, 226-264 |
| custom\_components/roommind/binary\_sensor.py                      |       38 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |      410 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      176 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      233 |        2 |     99% |   83, 115 |
| custom\_components/roommind/control/direct\_valve.py               |      115 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py             |     1414 |       33 |     98% |262, 308-309, 382-383, 389-390, 402-412, 730-732, 750-751, 815-822, 1058, 2052, 2055, 2176-2185, 2200, 2619, 3121, 3123, 3134, 3136, 3141, 3146, 3168, 3170 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      388 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       48 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      569 |        7 |     99% |529, 1339, 1366-1370 |
| custom\_components/roommind/coordinator.py                         |     1350 |       42 |     97% |510-511, 1367-1368, 1378, 1380, 1944, 1995, 2023-2024, 2075, 2284, 2490-2493, 2771, 2780, 2802, 2807, 2809, 2812, 2815, 2859, 2864-2869, 2873, 2913, 2915, 2918, 2921, 2947-2948, 3064, 3084-3092, 3110-3111, 3126-3131, 3148-3149 |
| custom\_components/roommind/deprecation.py                         |       56 |        0 |    100% |           |
| custom\_components/roommind/diagnostics.py                         |      238 |        0 |    100% |           |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/ac\_coil\_dry\_manager.py     |      248 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      186 |        2 |     99% |  125, 223 |
| custom\_components/roommind/managers/cover\_manager.py             |      209 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      267 |        1 |     99% |       202 |
| custom\_components/roommind/managers/device\_setpoint\_tracker.py  |      102 |        0 |    100% |           |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       71 |        0 |    100% |           |
| custom\_components/roommind/managers/head\_offset\_tracker.py      |       67 |        2 |     97% |    97, 99 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      130 |        2 |     98% |   72, 221 |
| custom\_components/roommind/managers/mold\_manager.py              |       86 |        0 |    100% |           |
| custom\_components/roommind/managers/price\_manager.py             |       87 |        0 |    100% |           |
| custom\_components/roommind/managers/recent\_temps.py              |       66 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |      169 |        4 |     98% |149, 152, 221-222 |
| custom\_components/roommind/managers/valve\_manager.py             |      112 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       93 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |       55 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      205 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_stats.py           |      183 |        3 |     98% |88, 95, 123 |
| custom\_components/roommind/store.py                               |      184 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      114 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/area\_utils.py                   |       18 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      201 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      147 |        2 |     99% |     70-71 |
| custom\_components/roommind/utils/mold\_utils.py                   |       33 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       49 |        0 |    100% |           |
| custom\_components/roommind/utils/price\_utils.py                  |      198 |        6 |     97% |88, 174, 211-214 |
| custom\_components/roommind/utils/schedule\_utils.py               |      263 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      360 |        3 |     99% |638, 877-882 |
| **TOTAL**                                                          | **9359** |  **212** | **98%** |           |


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