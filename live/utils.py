import asyncio
from anchorpy import Program, Provider, Wallet, Idl
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
import base58  
import base64
from solders.pubkey import Pubkey
from borsh_construct import CStruct, I64, U64, U128, U8
from construct import Bytes
from live.config import SOLANA_RPC_URL, RPC_CANDIDATES


RPC_URL = SOLANA_RPC_URL
JLP_MINT = "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4"  # JLP mint 地址

PROGRAM_ID = Pubkey.from_string("PERPHjGBqRHArX4DySjwM6UJHiR3sWAatqfdBS2qQJu")

POOL_ADDRESS = "5BUwFW4nRbftYTDMbgxykoFWqWHPzahFSNAaaaJtVKsq" # Jupiter Labs Perpetuals Markets (JLP Pool)
JUPITER_LABS_PERPETUALS_MARKETS = Pubkey.from_string("5BUwFW4nRbftYTDMbgxykoFWqWHPzahFSNAaaaJtVKsq")

VAULT_AUTHORITY = "AVzP2GeRmqGphJsMxWoqjpUifPpCret7LqWhD8NWQK49"  # Jupiter Perpetuals Vault Authority

from pathlib import Path
IDL_PATH = str(Path(__file__).with_name("jupiter_perpetuals_idl.json"))

CUSTODIES = {
    "SOL": "7xS2gz2bTp3fwCC7knJvUWTEU9Tycczu6VhJYKgi1wdz",
    "ETH": "AQCGyheWPLeo6Qp9WpYS9m3Qj479t7R636N9ey1rEjEn",
    "BTC": "5Pv3gM9JrFFH883SWAhvJC9RPYmo8UNxuFtv5bMMALkm",
}


SYMBOL = {
    '3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh': 'BTC',
    '7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs': 'ETH',
    'So11111111111111111111111111111111111111112': 'SOL',
    'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB': 'USDT',
    'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v': 'USDC'
}

CUSTODY_TO_SYMBOL = {
    Pubkey.from_string("7xS2gz2bTp3fwCC7knJvUWTEU9Tycczu6VhJYKgi1wdz"): "SOL",
    Pubkey.from_string("AQCGyheWPLeo6Qp9WpYS9m3Qj479t7R636N9ey1rEjEn"): "ETH",
    Pubkey.from_string("5Pv3gM9JrFFH883SWAhvJC9RPYmo8UNxuFtv5bMMALkm"): "BTC",
}

DECIMALS = {"SOL": 9, "ETH": 6, "BTC": 6}

# 全局单例客户端，避免每次调用都创建新客户端
_global_async_client = None
_global_sync_client = None
_client_lock = asyncio.Lock()


async def _get_async_client() -> AsyncClient:
    """获取全局单例 AsyncClient"""
    global _global_async_client

    async with _client_lock:
        if _global_async_client is not None:
            # 检查客户端是否还活着
            try:
                await _global_async_client.get_slot()
                return _global_async_client
            except Exception:
                # 客户端已失效，关闭并重建
                try:
                    await _global_async_client.close()
                except:
                    pass
                _global_async_client = None

        # 创建新客户端
        for url in RPC_CANDIDATES:
            c = AsyncClient(url)
            try:
                await c.get_slot()
                _global_async_client = c
                return c
            except Exception:
                await c.close()
                continue

        # 如果所有候选都失败，使用默认 URL
        _global_async_client = AsyncClient(RPC_URL)
        return _global_async_client

def _get_sync_client():
    """获取全局单例同步 Client"""
    global _global_sync_client

    if _global_sync_client is not None:
        # 检查客户端是否还活着
        try:
            _global_sync_client.get_slot()
            return _global_sync_client
        except Exception:
            # 客户端已失效，重建
            _global_sync_client = None

    # 创建新客户端
    from solana.rpc.api import Client
    for url in RPC_CANDIDATES:
        try:
            c = Client(url)
            c.get_slot()
            _global_sync_client = c
            return c
        except Exception:
            continue

    # 如果所有候选都失败，使用默认 URL
    _global_sync_client = Client(RPC_URL)
    return _global_sync_client

async def rpc_call_async(method, params):
    """异步 RPC 调用函数 - 使用全局单例客户端"""
    client = await _get_async_client()
    try:
        if method == "getTokenSupply":
            # 示例: 针对getTokenSupply的异步调用
            result = await client.get_token_supply(Pubkey.from_string(params[0]))
            return {"value": {"uiAmount": str(result.value.ui_amount)}}
        elif method == "getAccountInfo":
            # 针对getAccountInfo
            result = await client.get_account_info(Pubkey.from_string(params[0]), encoding=params[1]["encoding"])
            if result.value:
                data_b64 = base64.b64encode(result.value.data).decode()
                return {"value": {"data": [data_b64]}}
            return {"value": None}
        elif method == "getTokenAccountBalance":
            # 针对getTokenAccountBalance
            result = await client.get_token_account_balance(Pubkey.from_string(params[0]))
            return {"value": {"uiAmount": float(result.value.ui_amount) if result.value else 0.0}}
        else:
            # 通用fallback,如果有其他方法,可以扩展
            raise ValueError(f"Unsupported method: {method}")
    except Exception as e:
        print(f"异步 RPC 调用失败: {e}")
        return None
    # 注意：不再关闭客户端，因为是全局单例

async def get_jlp_supply_async() -> float:
    """异步获取 JLP 总供应量, 返回 token 数量"""
    supply_info = await rpc_call_async("getTokenSupply", [JLP_MINT])
    return float(supply_info["value"]["uiAmount"])

async def get_spot_liquidity_async(asset: str) -> float:
    """异步获取单个资产的 spotLiquidity (unstaked from ATA), 返回 token 数量"""
    custody = CUSTODIES[asset]
    account_info = await rpc_call_async("getAccountInfo", [custody, {"encoding": "base64"}])
    
    raw_data_b64 = account_info["value"]["data"][0]
    raw_data = base64.b64decode(raw_data_b64)
    
    # 解析 token_account Pubkey (offset 72: 32 bytes)
    token_account_bytes = raw_data[72: 104]
    token_account = base58.b58encode(token_account_bytes).decode()

    # 获取 ATA 余额 (spot liquidity, unstaked)
    balance_info = await rpc_call_async("getTokenAccountBalance", [token_account])
    spot_tokens = float(balance_info["value"]["uiAmount"])
    
    return spot_tokens

async def get_staked_sol_async() -> float:
    """
    异步获取 JLP 池 staked SOL 总数量 (using account.lamports as proxy for delegated amount)
    """
    # 使用 asyncio.to_thread 包装同步代码,避免 AsyncClient 的 MemcmpOpts 问题
    def sync_get_staked():
        from solders.pubkey import Pubkey
        from solana.rpc.types import MemcmpOpts

        # 使用全局单例客户端
        connection = _get_sync_client()

        # Stake Program ID
        stake_program_id = Pubkey.from_string("Stake11111111111111111111111111111111111111")

        # 获取所有由该钱包拥有的质押账户 (filter withdraw authority at offset 44)
        response = connection.get_program_accounts(
            stake_program_id,
            filters=[MemcmpOpts(offset=44, bytes=VAULT_AUTHORITY)]
        )

        total_staked = 0.0

        # 解析每个质押账户
        for account_info in response.value:
            stake_lamports = account_info.account.lamports
            stake_sol = stake_lamports
            total_staked += stake_sol

        return total_staked / 10**9

    # Python 3.9+: await asyncio.to_thread(sync_get_staked)
    # 或兼容旧版: await asyncio.get_event_loop().run_in_executor(None, sync_get_staked)
    return await asyncio.to_thread(sync_get_staked)

POSITION_LAYOUT = CStruct(
    "owner" / Bytes(32),
    "pool" / Bytes(32),
    "custody" / Bytes(32),
    "collateral_custody" / Bytes(32),
    "open_time" / I64,
    "update_time" / I64,
    "side" / U8,  # 1=Long, 2=Short
    "price" / U64,
    "size_usd" / U64,
    "collateral_usd" / U64,
    "realised_pnl_usd" / I64,
    "cumulative_interest_snapshot" / U128,
    "locked_amount" / U64,
    "bump" / U8,
)

def parse_position_data(account_data: bytes):
    try:
        if len(account_data) < 8:
            return None, None, 0
        decoded = POSITION_LAYOUT.parse(account_data[8:])
        custody_pk = Pubkey.from_bytes(decoded.custody)
        symbol = CUSTODY_TO_SYMBOL.get(custody_pk, "UNKNOWN")
        if symbol == "UNKNOWN":
            return None, None, 0
        side_str = "long" if decoded.side == 1 else "short" if decoded.side == 2 else "unknown"
        if side_str == "unknown":
            return None, None, 0
        size_usd = decoded.size_usd  
        price = decoded.price    
        number_of_tokens = size_usd / price if price > 0 else 0
        return symbol, side_str, number_of_tokens
    except Exception as e:
        print(f"Parse error: {e}")
        return None, None, 0


async def get_positions_by_asset_async():
    # 使用 asyncio.to_thread 包装同步代码,避免 AsyncClient 的 MemcmpOpts 问题
    def sync_get_positions():
        from solders.pubkey import Pubkey
        from solana.rpc.types import MemcmpOpts
        from base64 import b64decode
        # 注意:parse_position_data 和其他依赖函数需在此作用域可用,或导入/定义在这里
        # 假设 parse_position_data 已定义在全局

        # 使用全局单例客户端
        client = _get_sync_client()

        filters = [
            216,
            MemcmpOpts(offset=40, bytes=str(JUPITER_LABS_PERPETUALS_MARKETS)),  # match pool after owner, with discriminator
        ]
        response = client.get_program_accounts(PROGRAM_ID, encoding="base64", filters=filters)
        aggregates = {}

        for acc_info in response.value:
            try:
                data_field = acc_info.account.data
                if isinstance(data_field, (bytes, bytearray)):
                    raw = bytes(data_field)
                elif isinstance(data_field, list) and len(data_field) >= 1 and isinstance(data_field[0], str):
                    raw = b64decode(data_field[0])
                elif isinstance(data_field, str):
                    raw = b64decode(data_field)
                else:
                    continue
                symbol, side, size = parse_position_data(raw)
                if symbol and side:
                    if symbol not in aggregates:
                        aggregates[symbol] = {'long': 0.0, 'short': 0.0}
                    aggregates[symbol][side] += size
            except Exception as e:
                print(e)
                continue

        return aggregates

    return await asyncio.to_thread(sync_get_positions)


async def fetch_fees_reserves_async():
    # 使用全局单例客户端
    client = await _get_async_client()

    # Load a dummy keypair (for read-only operations, no signing needed)
    keypair = Keypair()
    wallet = Wallet(keypair)
    provider = Provider(client, wallet)


    with open(IDL_PATH, 'r') as f:
        idl_json = f.read()  # Read as raw JSON string

    # Parse the IDL
    try:
        idl = Idl.from_json(idl_json)
    except Exception as e:
        print(f"Error parsing IDL: {e}")
        raise

    # Initialize the Anchor program
    try:
        program = Program(idl, PROGRAM_ID, provider)
    except Exception as e:
        print(f"Error initializing program: {e}")
        raise

    try:
        # Fetch the Pool account
        pool_pubkey = Pubkey.from_string(POOL_ADDRESS)
        pool_account = await program.account["Pool"].fetch(pool_pubkey)
        custodies = pool_account.custodies

        fees_data = {}
        for custody_pubkey in custodies:
            custody_account = await program.account["Custody"].fetch(custody_pubkey)

            # Extract feesReserves from assets
            fees_raw = custody_account.assets.fees_reserves
            decimals = custody_account.decimals
            fees_human = fees_raw / (10 ** decimals)

            mint_str = str(custody_account.mint)
            fees_data[SYMBOL[mint_str]] = fees_human
        return fees_data

    except Exception as e:
        print(f"Error fetching accounts: {e}")
        raise

    # 注意：不再关闭客户端，因为是全局单例


async def cleanup_global_clients():
    """清理全局客户端资源"""
    global _global_async_client, _global_sync_client

    if _global_async_client:
        try:
            await _global_async_client.close()
        except:
            pass
        _global_async_client = None

    if _global_sync_client:
        try:
            _global_sync_client._provider.session.close()
        except:
            pass
        _global_sync_client = None


async def cal_delta_for_asset_async(symbol: str, jlp_supply: float, positions: dict, undistributed_fees: dict) -> float:
    """异步计算单个资产的 delta"""
    spot_tokens = await get_spot_liquidity_async(symbol)
    
    # 对于 SOL,额外添加 staked SOL
    if symbol == 'SOL':
        staked_sol = await get_staked_sol_async()
        spot_tokens += staked_sol
    
    fees_tokens = undistributed_fees.get(symbol, 0.0)
    spot_fee_tokens = spot_tokens + fees_tokens
    long_tokens = positions.get(symbol, {}).get('long', 0.0)
    short_tokens = positions.get(symbol, {}).get('short', 0.0)
    delta = (spot_fee_tokens - long_tokens + short_tokens) / jlp_supply
    
    print(f"{symbol} : spot {spot_tokens:.2f}, fees {fees_tokens:.2f}, spot+fees {spot_fee_tokens:.2f}, long {long_tokens:.2f}, short {short_tokens:.2f}, jlp_supply {jlp_supply:.2f}, delta {delta:.8f}")
    
    return delta

async def cal_delta_async() -> dict:
    """异步核心计算逻辑"""
    # 并行获取公共数据
    tasks = [
        get_jlp_supply_async(),
        get_positions_by_asset_async(),
        fetch_fees_reserves_async()
    ]
    jlp_supply, positions, undistributed_fees = await asyncio.gather(*tasks)
    
    # 并行计算每个资产的 delta
    symbols = ['SOL', 'ETH', 'BTC']
    delta_tasks = [cal_delta_for_asset_async(symbol, jlp_supply, positions, undistributed_fees) for symbol in symbols]
    deltas = await asyncio.gather(*delta_tasks)
    
    delta_dict = dict(zip(symbols, deltas))
    return delta_dict



if __name__ == "__main__":
    jlp_supply = asyncio.run(get_jlp_supply_async())
    print(f"JLP Supply: {jlp_supply}")

    spot_sol = asyncio.run(get_spot_liquidity_async("SOL"))
    print(f"Spot SOL: {spot_sol:.2f}")

    spot_eth = asyncio.run(get_spot_liquidity_async("ETH"))
    print(f"Spot ETH: {spot_eth:.2f}")

    spot_btc = asyncio.run(get_spot_liquidity_async("BTC"))
    print(f"Spot BTC: {spot_btc:.2f}")


    staked_sol = asyncio.run(get_staked_sol_async())
    print(f"Staked SOL: {staked_sol:.2f}")

    positions = asyncio.run(get_positions_by_asset_async())
    print("Positions:", positions)  

    undistributed_fees = asyncio.run(fetch_fees_reserves_async())
    print("Fees Reserves:", undistributed_fees)

    delta = asyncio.run(cal_delta_async())
    print("Delta:", delta)
