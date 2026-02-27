import os

def _load_env_file(path: str = ".env") -> None:
    try:
        p = os.getenv("HJLP_ENV_PATH", path)
        if not p:
            return
        if not os.path.exists(p):
            return
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and (k not in os.environ or os.environ[k] == ""):
                    os.environ[k] = v
    except Exception:
        pass

_load_env_file()

def env_str(k: str, default: str = "") -> str:
    v = os.getenv(k)
    return v if v not in (None, "") else default

def env_int(k: str, default: int) -> int:
    try:
        return int(env_str(k, str(default)))
    except Exception:
        return default

def env_float(k: str, default: float) -> float:
    try:
        return float(env_str(k, str(default)))
    except Exception:
        return default

def env_list(k: str, default: list) -> list:
    s = env_str(k, "")
    if s in (None, ""):
        return default
    items = [x.strip() for x in s.replace("\n", ",").split(",")]
    return [x for x in items if x]

SOLANA_RPC_URL = env_str("SOLANA_RPC_URL", "https://solana-rpc.publicnode.com")
HJLP_ADAPTER = env_str("HJLP_ADAPTER", "dummy").lower()

RPC_CANDIDATES = env_list("RPC_CANDIDATES", [SOLANA_RPC_URL])
DINGTALK_ACCESS_TOKEN = env_str("DINGTALK_ACCESS_TOKEN", "")
DINGTALK_SECRET = env_str("DINGTALK_SECRET", "")
