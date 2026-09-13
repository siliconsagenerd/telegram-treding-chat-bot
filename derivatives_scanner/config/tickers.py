from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class MarketConfig:
    key: str
    timezone: str
    session_start: tuple[int, int]
    session_end: tuple[int, int]
    tickers: list[str]


US_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "ORCL", "AVGO", "SPCX",
    "GWRE", "LULU", "PATH", "ASAN", "NLST", "SNPS", "ZS", "NFLX", "TTD", "PLTR",
    "WDAY", "SNOW", "FIG", "SPOT", "DASH", "RPD", "NOW", "HPE", "MRNA", "AI",
    "NIO", "TEAM", "RKT", "PL", "SEZL", "MDB", "MSTR", "SOFI", "SOUN", "CRM",
    "AMCR", "B", "QBTS", "NEM", "PFG", "MOVE", "XOM", "CVX", "PFE", "ONDS",
    "CRWD", "HIMS", "SLNH", "TRMB", "SSL", "V", "CAVA", "RDDT", "CAH", "MA",
    "KLAR", "BLK", "CAE", "UBER", "NTAP", "META", "CCJ", "NLY", "SAP", "ACM",
    "LQDA", "SE", "ASTS", "STN", "QNT", "IBM", "VLO", "PANW", "RKLB", "TJX",
    "MPC", "SAIC", "SKYH", "GNSS", "HGRAF", "CSCO", "HD", "CIEN", "YEXT", "CVNA",
    "NVDA", "GLBE", "OKTA", "AMKR", "EAT", "APLD", "MDT", "ADI", "CLS", "CIFR",
    "DELL", "IOT", "PLUG", "TSM", "SLS", "APP", "FN", "NOK", "DOCU", "NBIS",
    "ARM", "INTC", "ASML", "AMAT", "CRDO", "AMD", "LITE", "MU", "BETA", "IREN",
    "FRVO", "MRVL", "SKHY", "SNDK", "ALAB", "CBRS",
]

INDIAN_TICKERS = [
    "ADANIENT.NS", "APOLLOHOSP.NS", "BPCL.NS", "CIPLA.NS", "EICHERMOT.NS",
    "HEROMOTOCO.NS", "HINDUNILVR.NS", "INDUSINDBK.NS", "JSWSTEEL.NS", 
    "NESTLEIND.NS", "SHRIRAMFIN.NS", "TATACONSUM.NS", "TECHM.NS", "WIPRO.NS",
    "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "AXISBANK.NS", "SBIN.NS",
    "KOTAKBANK.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "INFY.NS", "TCS.NS",
    "HCLTECH.NS", "BHARTIARTL.NS", "MARUTI.NS", "M&M.NS",
    "TATASTEEL.NS", "HINDALCO.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS",
    "SUNPHARMA.NS", "DRREDDY.NS", "TITAN.NS", "ASIANPAINT.NS",
    "COALINDIA.NS", "ADANIPORTS.NS", "GRASIM.NS", "BAJAJ-AUTO.NS",
    "CHOLAFIN.NS", "MUTHOOTFIN.NS",  "PFC.NS", "LICHSGFIN.NS",
    "IDFCFIRSTB.NS", "BANDHANBNK.NS", "CANBK.NS", "PNB.NS", "BANKBARODA.NS",
    "FEDERALBNK.NS", "AUBANK.NS", "M&MFIN.NS", "MANAPPURAM.NS", "HDFCAMC.NS",
    "PERSISTENT.NS", "KPITTECH.NS", "LTTS.NS", "COFORGE.NS", "MPHASIS.NS",
    "TATACOMM.NS", "INDUSTOWER.NS", "IDEA.NS", "DIXON.NS", "ETERNAL.NS",
    "PAYTM.NS", "NYKAA.NS", "TATAELXSI.NS", 
    "TVSMOTOR.NS", "TIINDIA.NS", "BOSCHLTD.NS", "MRF.NS", "BALKRISIND.NS",
     "BHARATFORG.NS", "SONACOMS.NS", "EXIDEIND.NS", "ARE&M.NS",
    "ASHOKLEY.NS", "ESCORTS.NS", "APOLLOTYRE.NS", "MOTHERSON.NS",
    "JINDALSTEL.NS", "SAIL.NS", "NMDC.NS", "VEDL.NS", "NATIONALUM.NS",
    "HINDZINC.NS", "APLAPOLLO.NS", "OIL.NS", "GAIL.NS", "RECLTD.NS",
    "ADANIPOWER.NS", "ADANIGREEN.NS", "ATGL.NS", "TATAPOWER.NS", "JSWENERGY.NS",
    "NHPC.NS", "SJVN.NS", "IEX.NS", "PETRONET.NS", "BEL.NS", "HAL.NS",
    "BHEL.NS", "CUMMINSIND.NS", "ABB.NS", "SIEMENS.NS", "IRCTC.NS",
    "CONCOR.NS", "NCC.NS", "IRFC.NS", "RVNL.NS", "MAZDOCK.NS",
    "LUPIN.NS", "AUROPHARMA.NS", "BIOCON.NS", "GLENMARK.NS", "TORNTPHARM.NS",
    "PIDILITIND.NS", "SRF.NS", "UPL.NS", "TATACHEM.NS", "DEEPAKNTR.NS", "COROMANDEL.NS",
]

EU_TICKERS = [
    "ASML.AS", "SAP.DE", "SIE.DE", "MC.PA", "TTE.PA", "ALV.DE", "SAN.MC",
    "SU.PA", "OR.PA", "AIR.PA", "IBE.MC", "DTE.DE", "BNP.PA", "VOW3.DE",
    "MBG.DE", "ENI.MI", "BAS.DE", "MUV2.DE", "IFX.DE", "ABI.BR", "BMW.DE",
    "DPW.DE", "BOS3.DE", "FRE.DE", "RWE.DE", "BAYN.DE", "VNA.DE", "HEI.DE",
    "EOAN.DE", "DBK.DE", "KER.PA", "RMS.PA", "SAF.PA", "SGO.PA", "STMPA.PA",
    "VIE.PA", "ACA.PA", "BN.PA", "CA.PA", "DG.PA", "ML.PA", "RI.PA", "RNO.PA",
    "PUB.PA", "VIV.PA", 
    "ASM.AS", "BESI.AS",  "ATO.PA", "CAP.PA",
    "NOKIA.HE", "ERIC-B.ST", "LOGN.SW", "AMS.VI", "SOON.SW", "TEMN.SW",
    "RHM.DE", "LDO.MI", "MTX.DE", "ALO.PA", "GEA.DE", "ANDR.VI", "SKF-B.ST",
    "SAND.ST", "EPI-B.ST", "VOLV-B.ST", "F.MI", "PUM.DE", "BOSS.DE",
    "STLAM.MI", "P911.DE", "CON.DE", "PRE.MI", "BRE.MI",
    "CBK.DE", "BBVA.MC", "ISP.MI", "UCG.MI", "INGA.AS", "ABN.AS", "KBC.BR",
    "AGS.BR", "CS.PA", "G.MI",
    "REP.MC", "GALP.LS", "OMV.VI", "AKRBP.OL", "NHY.OL", "EVK.DE", "WIE.VI",
    "SOLB.BR", "UMI.BR", "AKE.PA", "FME.DE", "SAN.PA", "MRK.DE", "SASY.PA",
    "GEN.CO", "UCB.BR", "QIA.DE", "EVT.DE", "DIA.MI", "REC.MI", "VLA.PA",
]

MARKET_CONFIGS: dict[str, MarketConfig] = {
    "us": MarketConfig("us", "America/New_York", (9, 30), (16, 0), US_TICKERS),
    "europe": MarketConfig("europe", "Europe/Berlin", (9, 0), (17, 30), EU_TICKERS),
    "india": MarketConfig("india", "Asia/Kolkata", (9, 15), (15, 30), INDIAN_TICKERS),
}

REGION_ALIASES = {
    "us": "us",
    "america": "us",
    "all": "all",
    "eu": "europe",
    "europe": "europe",
    "in": "india",
    "india": "india",
}


def _dedupe_upper(symbols: list[str]) -> list[str]:
    normalized = [s.strip().upper() for s in symbols if s and s.strip()]
    return list(dict.fromkeys(normalized))


def _normalize_region(region: str | None) -> str:
    if not region:
        return "all"
    return REGION_ALIASES.get(region.strip().lower(), "all")


def _selected_markets() -> list[str]:
    raw = os.environ.get("SCANNER_MARKET", "us").strip().lower()
    if not raw:
        return ["us"]
    if raw == "all":
        return ["us", "europe", "india"]
    markets = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return [market for market in markets if market in MARKET_CONFIGS] or ["us"]


def is_market_open(market: str, now: datetime | None = None) -> bool:
    config = MARKET_CONFIGS[market]
    current = now or datetime.now(ZoneInfo(config.timezone))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo(config.timezone))
    else:
        current = current.astimezone(ZoneInfo(config.timezone))

    start = current.replace(
        hour=config.session_start[0],
        minute=config.session_start[1],
        second=0,
        microsecond=0,
    )
    end = current.replace(
        hour=config.session_end[0],
        minute=config.session_end[1],
        second=0,
        microsecond=0,
    )
    return start <= current <= end


def _markets_for_region(region: str | None) -> list[str]:
    normalized = _normalize_region(region)
    if normalized == "all":
        return ["us", "europe", "india"]
    return [normalized]


def get_tickers(region: str | None = None, live_only: bool = True) -> list[str]:
    override = os.environ.get("SCANNER_TICKERS", "").strip()
    if override:
        return _dedupe_upper(override.split(","))

    tickers: list[str] = []
    for market in _markets_for_region(region):
        if not live_only or is_market_open(market):
            tickers.extend(MARKET_CONFIGS[market].tickers)
    return _dedupe_upper(tickers)


__all__ = [
    "US_TICKERS",
    "INDIAN_TICKERS",
    "EU_TICKERS",
    "MARKET_CONFIGS",
    "get_tickers",
    "is_market_open",
]
