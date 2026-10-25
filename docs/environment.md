# Environment

- OS: Fedora Linux 43 (Workstation Edition), kernel 7.1.13-100.fc43.x86_64, x86_64
- Python: 3.12.14 (uv-managed, venv at `.venv`)
- uv: 0.12.10
- Resolved: 2026-10-25

System Python on this machine is 3.14. contree-sdk 0.3.6 declares `>=3.10,<3.15`, but its dev docs only list 3.10–3.13, so this project uses 3.12.

## Direct dependencies (pinned in pyproject.toml)

| Package | Version | Group |
|---|---|---|
| openai | 3.37.0 | runtime |
| contree-sdk | 0.3.6 | runtime |
| python-dotenv | 1.2.4 | runtime |
| rich | 15.0.0 | runtime |
| jinja2 | 3.1.6 | runtime |
| datasets | 5.1.0 | runtime |
| pytest | 9.1.1 | dev |
| pytest-asyncio | 1.4.0 | dev |
| ruff | 0.17.2 | dev |

## Full resolved set (`uv pip freeze`)

```
aiofiles==25.1.0
aiohappyeyeballs==2.7.1
aiohttp==3.14.5
aiosignal==1.4.0
annotated-types==0.8.0
anyio==4.15.1
attrs==26.1.0
cattrs==26.2.1
certifi==2026.10.23
click==8.5.0
contree-sdk==0.3.6
datasets==5.1.0
dill==0.4.1
filelock==4.2.4
frozenlist==1.8.0
fsspec==2026.7.0
h11==0.16.0
hf-xet==1.7.0
httpcore==1.0.9
httpcore2==2.16.0
httpx==0.28.1
httpx2==2.16.0
huggingface-hub==2.3.0
idna==3.20
iniconfig==2.3.1
jinja2==3.1.6
jiter==0.18.0
markdown-it-py==4.2.0
markupsafe==3.0.4
mdurl==0.1.2
multidict==7.2.1
multiprocess==0.70.19
numpy==2.5.4
openai==3.37.0
packaging==26.3
pandas==3.1.0
pluggy==1.7.0
propcache==0.5.4
pyarrow==26.0.0
pydantic==2.14.1
pydantic-core==2.50.1
pygments==2.21.0
pytest==9.1.1
pytest-asyncio==1.4.0
python-dateutil==3.0.0
python-dotenv==1.2.4
pyyaml==6.0.3
rich==15.0.0
ruff==0.17.2
six==1.17.0
sniffio==1.3.1
strenum==0.4.15
tqdm==4.70.1
truststore==0.10.5
typing-extensions==4.16.0
typing-inspection==0.4.4
tzdata==2026.5
xxhash==4.0.2
yarl==1.25.1
```
