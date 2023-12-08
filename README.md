# GitBugs-Java

GitBugs-Java is a reproducible Java benchmark of recent bugs.

[Visualization](https://www.nuno.saavedra.pt/gitbugs-java)

## Setup GitBugs-Java

Requirements:
- Python
- Poetry
- Docker

1. Setup Python environment
```bash
poetry shell
poetry install
```

2. Add GitBugs-Java and custom Act version to path
```bash
export PATH="$(pwd):$(pwd)/bin:$PATH"
```

3. Run Setup (Installs Docker Image ~50GiB, downloads required dependencies ~80GiB)
```bash
gitbugs-java setup
```

## Use GitBugs-Java

1. List all available project ids
```bash
gitbugs-java pids
```

2. List all available bug ids
```bash
gitbugs-java bids [-p=PID]
```

3. Checkout bug-fix
```bash
gitbugs-java checkout PID BID WORK_DIR [--fixed]
```

4. Run Actions
```bash
gitbugs-java run WORK_DIR
```

## Contents of GitBugs-Java

Please refer to the paper
