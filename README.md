# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/snazzybean/roommind/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                               |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------------------------------------- | -------: | -------: | ------: | --------: |
| custom\_components/roommind/\_\_init\_\_.py                        |      117 |       87 |     26% |35-37, 43-66, 71-72, 78-116, 121-132, 146-169, 174-212 |
| custom\_components/roommind/binary\_sensor.py                      |       37 |        0 |    100% |           |
| custom\_components/roommind/climate.py                             |      409 |        0 |    100% |           |
| custom\_components/roommind/config\_flow.py                        |       11 |       11 |      0% |      3-23 |
| custom\_components/roommind/const.py                               |      150 |        0 |    100% |           |
| custom\_components/roommind/control/\_\_init\_\_.py                |        0 |        0 |    100% |           |
| custom\_components/roommind/control/analytics\_simulator.py        |      232 |        2 |     99% |   81, 113 |
| custom\_components/roommind/control/direct\_valve.py               |      109 |        0 |    100% |           |
| custom\_components/roommind/control/mpc\_controller.py             |     1368 |       33 |     98% |232, 278-279, 351-352, 358-359, 371-381, 699-701, 719-720, 784-791, 1027, 1989, 1992, 2113-2122, 2137, 2531, 3005, 3007, 3018, 3020, 3025, 3030, 3052, 3054 |
| custom\_components/roommind/control/mpc\_optimizer.py              |      306 |        0 |    100% |           |
| custom\_components/roommind/control/residual\_heat.py              |       34 |        0 |    100% |           |
| custom\_components/roommind/control/solar.py                       |       81 |        1 |     99% |        72 |
| custom\_components/roommind/control/thermal\_model.py              |      480 |       17 |     96% |434, 943-951, 1069, 1198, 1205-1209 |
| custom\_components/roommind/coordinator.py                         |     1166 |       51 |     96% |437-438, 1132-1133, 1143, 1145, 1682, 1733, 1761-1762, 1813, 2173-2176, 2354-2356, 2360-2366, 2370, 2379, 2401, 2406, 2408, 2411, 2414, 2458, 2463-2468, 2472, 2512, 2514, 2517, 2520, 2538-2539, 2655, 2675-2683, 2701-2702, 2717-2722, 2739-2740 |
| custom\_components/roommind/deprecation.py                         |       56 |        0 |    100% |           |
| custom\_components/roommind/diagnostics.py                         |      231 |        0 |    100% |           |
| custom\_components/roommind/managers/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/managers/ac\_coil\_dry\_manager.py     |      248 |        0 |    100% |           |
| custom\_components/roommind/managers/compressor\_group\_manager.py |      186 |        2 |     99% |  125, 223 |
| custom\_components/roommind/managers/cover\_manager.py             |      204 |        0 |    100% |           |
| custom\_components/roommind/managers/cover\_orchestrator.py        |      243 |        2 |     99% |   85, 197 |
| custom\_components/roommind/managers/ekf\_training\_manager.py     |       71 |        1 |     99% |        38 |
| custom\_components/roommind/managers/head\_offset\_tracker.py      |       67 |        2 |     97% |    97, 99 |
| custom\_components/roommind/managers/heat\_source\_orchestrator.py |      123 |        2 |     98% |   71, 211 |
| custom\_components/roommind/managers/mold\_manager.py              |       71 |        0 |    100% |           |
| custom\_components/roommind/managers/residual\_heat\_tracker.py    |       69 |        0 |    100% |           |
| custom\_components/roommind/managers/valve\_manager.py             |      112 |        0 |    100% |           |
| custom\_components/roommind/managers/weather\_manager.py           |       59 |        0 |    100% |           |
| custom\_components/roommind/managers/window\_manager.py            |       93 |        0 |    100% |           |
| custom\_components/roommind/repairs.py                             |       15 |        0 |    100% |           |
| custom\_components/roommind/sensor.py                              |       54 |        0 |    100% |           |
| custom\_components/roommind/services/\_\_init\_\_.py               |        0 |        0 |    100% |           |
| custom\_components/roommind/services/analytics\_service.py         |      171 |        0 |    100% |           |
| custom\_components/roommind/store.py                               |      184 |        0 |    100% |           |
| custom\_components/roommind/switch.py                              |       96 |        0 |    100% |           |
| custom\_components/roommind/utils/\_\_init\_\_.py                  |        0 |        0 |    100% |           |
| custom\_components/roommind/utils/device\_utils.py                 |      191 |        0 |    100% |           |
| custom\_components/roommind/utils/history\_store.py                |      146 |        2 |     99% |     62-63 |
| custom\_components/roommind/utils/mold\_utils.py                   |       33 |        0 |    100% |           |
| custom\_components/roommind/utils/notification\_utils.py           |       50 |        0 |    100% |           |
| custom\_components/roommind/utils/presence\_utils.py               |       49 |        0 |    100% |           |
| custom\_components/roommind/utils/schedule\_utils.py               |      209 |        0 |    100% |           |
| custom\_components/roommind/utils/sensor\_utils.py                 |       29 |        1 |     97% |        25 |
| custom\_components/roommind/utils/temp\_utils.py                   |       26 |        0 |    100% |           |
| custom\_components/roommind/websocket\_api.py                      |      319 |        2 |     99% |   791-796 |
| **TOTAL**                                                          | **7905** |  **216** | **97%** |           |


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