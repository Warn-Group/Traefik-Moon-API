# Moon-API

## Installation

### Prerequisites

- Python >= 3.10

### Installation

#### Global environment

1. Install dependencies `pip install -r ./requirements.txt`
2. Run the API `python -m hypercorn --bind '127.0.0.1:8008' --worker-class=trio 'api/main:app_factory()'`

#### Using venv

1. Create venv `python -m venv .venv`
2. Activate venv
    a. On Windows `.venv\Scripts\activate`
    b. Linux/MacOS `source .venv/bin/activate`
3. Install dependencies `pip install -r ./requirements.txt`
4. Run the API `python -m hypercorn --bind '127.0.0.1:8008' --worker-class=trio 'api/main:app_factory()'`

#### Using Docker

1. `docker compose up`
