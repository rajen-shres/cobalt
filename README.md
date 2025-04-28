[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)[![GPL license](https://img.shields.io/badge/License-GPL-blue.svg)](https://github.com/mguthrieabf/cobalt/blob/master/LICENSE) ![GitHub repo size](https://img.shields.io/github/repo-size/abftech/cobalt) ![Lines of code](https://img.shields.io/tokei/lines/github/abftech/cobalt) ![GitHub last commit (branch)](https://img.shields.io/github/last-commit/abftech/cobalt/master)
# Cobalt - Work in Progress

Cobalt is a web-based platform for the administration and running of [the game of bridge](https://en.wikipedia.org/wiki/Contract_bridge). It is expected to be complete in 2023 or 2024.

Cobalt will manage all aspects of bridge administration for players, clubs, state organisations and national
organisations. This includes payments, event entry, club membership, discussion forums, masterpoints, results and scoring.
Cobalt will be extended to include teaching and online bridge once the core functions have been developed.

Initial development of Cobalt is funded by the [Australian Bridge Federation](http://abf.com.au).

Documentation at [docs.myabf.com.au](http://docs.myabf.com.au).

## License

See the [LICENSE](LICENSE) file for license rights and limitations (GPL).


## setup for dev.
run the docker-compose up -d 

this apps uses python 3.9. 
Create environment for:
>> pythorn -3.9 -m venv venv39

please check docker-compose.yml
And might need to add_model_default.sql
