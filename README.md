# Deliver-Me Backend Project

## Installation
- Install mysql@5.7
- Create DB named `deliver_me` on mysql
- Install Python version: 3.7.0
- Install Django and reqiements by using `pip`
```shell
pip install -r requirements.txt
mkdir logs
cp .env.sample .env
```
- Populate all vars on .env (Contact PM if you have doubt on a var)

* SECRET_KEY
```shell
from django.core.management.utils import get_random_secret_key
get_random_secret_key()
```
