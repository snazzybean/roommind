# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      150 |       90 |     40% |41-43, 49-76, 99-100, 106-144, 149-160, 176-199, 226-264 |
| custom\_components/roommind/binary\_sensor.py                      |       38 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |      412 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      159 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      232 |        2 |     99% |   81, 113 |
| custom\_components/roommind/control/direct\_valve.py               |      115 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py             |     1372 |       33 |     98% |234, 280-281, 353-354, 360-361, 373-383, 701-703, 721-722, 786-793, 1029, 1991, 1994, 2115-2124, 2139, 2558, 3032, 3034, 3045, 3047, 3052, 3057, 3079, 3081 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      306 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       34 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      480 |       17 |     96% |434, 943-951, 1069, 1198, 1205-1209 |
| custom\_components/roommind/coordinator.py                         |     1275 |       51 |     96% |490-491, 1266-1267, 1277, 1279, 1823, 1874, 1902-1903, 1954, 2335-2338, 2570-2572, 2576-2582, 2586, 2595, 2617, 2622, 2624, 2627, 2630, 2674, 2679-2684, 2688, 2728, 2730, 2733, 2736, 2762-2763, 2879, 2899-2907, 2925-2926, 2941-2946, 2963-2964 |
| custom\_components/roommind/deprecation.py                         |       56 |        0 |    100% |           |
| custom\_components/roommind/diagnostics.py                         |      231 |        0 |    100% |           |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/ac\_coil\_dry\_manager.py     |      248 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      186 |        2 |     99% |  125, 223 |
| custom\_components/roommind/managers/cover\_manager.py             |      209 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      267 |        2 |     99% |   85, 202 |
| custom\_components/roommind/managers/device\_setpoint\_tracker.py  |      102 |        0 |    100% |           |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       71 |        1 |     99% |        38 |
| custom\_components/roommind/managers/head\_offset\_tracker.py      |       67 |        2 |     97% |    97, 99 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      123 |        2 |     98% |   71, 211 |
| custom\_components/roommind/managers/mold\_manager.py              |       86 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       69 |        0 |    100% |           |
| custom\_components/roommind/managers/valve\_manager.py             |      112 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       93 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |       55 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      183 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_stats.py           |      120 |        0 |    100% |           |
| custom\_components/roommind/store.py                               |      184 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |      114 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/area\_utils.py                   |       18 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      201 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      147 |        2 |     99% |     67-68 |
| custom\_components/roommind/utils/mold\_utils.py                   |       33 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       49 |        0 |    100% |           |
| custom\_components/roommind/utils/schedule\_utils.py               |      235 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      342 |        3 |     99% |611, 843-848 |
| **TOTAL**                                                          | **8445** |  **220** | **97%** |           |


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