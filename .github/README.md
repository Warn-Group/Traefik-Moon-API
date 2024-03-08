# Moon-API

## Installation

### Prerequisites

- Python >= 3.9

### Installation

1. Install dependencies `pip install -r ./requirements.txt`
2. Run the API `python -m hypercorn --worker-class=trio "main:app_factory()"`