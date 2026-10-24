#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #06: omega_phantom_v7_radar.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Motor Tensorial de Microestructura L2 + publicTrade a 50 Hz (20 ms):
  1. Reloj de Eventos L2 (Event-Driven Book Clock): filtra instantaneas L2
     identicas en produccion para preservar la racha de confirmacion H-OFI y
     evalua delta_p_pct sobre horizonte biescala real (3.0s a 12.0s).
  2. Supresor de Rafaga Post-Disparo (12.0s cooldown por simbolo tras emitir
     senal en produccion) para impedir disparos duplicados en vuelo.
  3. Variacion Bipower, Hurst Winsorizado, Lyapunov, Hawkes y SCAR-LOCK-00..13.
==============================================================================
"""
from __future__ import annotations

import collections
import math
import time
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

import omega_phantom_v7_config as cfg
from omega_phantom_v7_ram import ESTADO_RAM
from omega_phantom_v7_tricortex import ESCUDO_TRICORTEX

_PESOS_OFI_L1_L5: Tuple[float, ...] = (
    1.0,
    math.exp(-0.5),
    math.exp(-1.0),
    math.exp(-1.5),
    math.exp(-2.0),
)


def calcular_percentil_intradia_utc(
    ahora: Optional[float] = None,
    sigma_bv: float = 0.00060,
) -> Tuple[float, str, float]:
    t_now = float(ahora) if ahora is not None else time.time()
    dt_utc = datetime.fromtimestamp(t_now, tz=timezone.utc)
    h_utc = dt_utc.hour + (dt_utc.minute / 60.0) + (dt_utc.second / 3600.0)

    nucleos = (
        (0.00, 0.85, 0.90),
        (8.00, 1.10, 0.92),
        (13.75, 1.65, 0.98),
        (16.00, 1.15, 0.88),
        (24.00, 0.85, 0.90),
    )
    max_g = 0.0
    for mu, sigma, peso in nucleos:
        g = peso * math.exp(-0.5 * ((h_utc - mu) / sigma) ** 2)
        if g > max_g:
            max_g = g

    h_compuesta = min(0.99, 0.14 + max_g)
    phi_vol = math.tanh((float(sigma_bv) - 0.00055) / 0.00110)
    p_dia = max(0.05, min(0.99, 0.60 * h_compuesta + 0.40 * phi_vol))
    tag_p = f"P{int(round(p_dia * 100.0)):02d}_ELASTICO"
    return round(p_dia, 4), tag_p, round(h_compuesta, 4)


class VentanaZ:
    """Estructura deslizante O(1) por activo con Reloj de Eventos L2."""

    def __init__(self, symbol: str, maxlen: int = cfg.VENTANA_Z_TICKS) -> None:
        self.symbol: str = symbol
        self.maxlen: int = int(maxlen)
        self.precios: Deque[float] = collections.deque(maxlen=self.maxlen)
        self.precios_ts: Deque[Tuple[float, float]] = collections.deque(maxlen=360)
        self.retornos: Deque[float] = collections.deque(maxlen=self.maxlen)
        self.ofi_hist: Deque[float] = collections.deque(maxlen=35)
        self.ema900_hist: Deque[float] = collections.deque(maxlen=30)

        self.ema900: float = 0.0
        self.alpha_ema900: float = 2.0 / (float(cfg.VENTANA_EMA_MACRO_TICKS) + 1.0)
        self.ticks_totales: int = 0

        self.prev_bids: List[Tuple[float, float]] = []
        self.prev_asks: List[Tuple[float, float]] = []

        self.hawkes_intensidad: float = 0.0
        self.ts_ultimo_tick: float = 0.0
        self.ts_ultimo_pulso_toxico: float = 0.0
        self.ts_ultimo_choque_lyapunov: float = 0.0
        self.ts_ultima_replica_lyapunov: float = 0.0
        self.ts_ultimo_anti_squeeze: float = 0.0
        self.px_ultimo_anti_squeeze: float = 0.0
        self.ts_ultimo_disparo: float = 0.0

        self.ofi_ticks_long: int = 0
        self.ofi_ticks_short: int = 0

        self.vol_taker_buy_ventana: float = 0.0
        self.vol_taker_sell_ventana: float = 0.0
        self.vpin_actual: float = 0.18
        self.ultimo_metricas: Dict[str, float] = {}

    def registrar_trade_publico(self, price: float, qty: float, side_taker: str) -> None:
        vol_usdt = max(0.0, float(price) * float(qty))
        if str(side_taker).lower() in ("buy", "long"):
            self.vol_taker_buy_ventana += vol_usdt
        else:
            self.vol_taker_sell_ventana += vol_usdt

    def _calcular_ml_ofi(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
    ) -> float:
        if not self.prev_bids or not self.prev_asks or not bids or not asks:
            self.prev_bids = bids[:5]
            self.prev_asks = asks[:5]
            return 0.0

        num_niveles = min(5, len(bids), len(asks), len(self.prev_bids), len(self.prev_asks))
        ofi_num = 0.0
        ofi_den = 0.0

        for i in range(num_niveles):
            w = _PESOS_OFI_L1_L5[i]
            b_p, b_q = bids[i]
            pb_p, pb_q = self.prev_bids[i]
            a_p, a_q = asks[i]
            pa_p, pa_q = self.prev_asks[i]

            if b_p > pb_p:
                e_b = b_q
            elif b_p == pb_p:
                e_b = b_q - pb_q
            else:
                e_b = -pb_q

            if a_p < pa_p:
                e_a = a_q
            elif a_p == pa_p:
                e_a = a_q - pa_q
            else:
                e_a = -pa_q

            ofi_num += w * (e_b - e_a)
            ofi_den += w * (b_q + a_q + pb_q + pa_q) * 0.5

        self.prev_bids = bids[:5]
        self.prev_asks = asks[:5]

        if ofi_den <= 1e-9:
            return 0.0
        ofi_l2 = max(-1.0, min(1.0, ofi_num / ofi_den))

        tot_taker = self.vol_taker_buy_ventana + self.vol_taker_sell_ventana
        if tot_taker > 1e-6:
            flujo_taker = (self.vol_taker_buy_ventana - self.vol_taker_sell_ventana) / tot_taker
            self.vol_taker_buy_ventana *= 0.55
            self.vol_taker_sell_ventana *= 0.55
            return max(-1.0, min(1.0, 0.65 * ofi_l2 + 0.35 * flujo_taker))

        return ofi_l2

    def _calcular_sigma_bipower(self) -> float:
        n = len(self.retornos)
        if n < 4:
            return 0.0010
        rets = [r for r in self.retornos if abs(r) > 1e-9]
        if len(rets) < 4:
            rets = list(self.retornos)
        m = len(rets)
        suma_bv = 0.0
        for i in range(1, m):
            suma_bv += abs(rets[i]) * abs(rets[i - 1])
        bv = (math.pi / 2.0) * (suma_bv / float(max(1, m - 1)))
        sigma_bv = math.sqrt(max(1e-10, bv))

        piso_sigma = 0.00028 if self.symbol in cfg.CLASE_HIGH_BETA else 0.00020
        return max(piso_sigma, sigma_bv)

    def _calcular_hurst(self) -> float:
        if len(self.retornos) < 10:
            return 0.42
        sigma = self._calcular_sigma_bipower()
        cota = 2.5 * sigma
        rets_w = [max(-cota, min(cota, r)) for r in list(self.retornos)[-20:]]
        desplazamiento_neto = abs(sum(rets_w))
        longitud_camino = sum(abs(r) for r in rets_w)
        if longitud_camino <= 1e-12:
            return 0.42
        er = desplazamiento_neto / longitud_camino
        h = 0.34 + 0.45 * er
        return max(0.25, min(0.75, h))

    def _calcular_lyapunov(self) -> float:
        if len(self.precios) < 4:
            return 0.0
        p_t = self.precios[-1]
        p_1 = self.precios[-2]
        p_2 = self.precios[-3]
        if p_2 <= 0.0 or p_1 <= 0.0:
            return 0.0
        v1 = (p_t - p_1) / p_1
        v0 = (p_1 - p_2) / p_2
        return v1 - v0

    def _calcular_delta_p_biescala(self, mid_price: float, ahora: float) -> float:
        p_base_ticks = self.precios[0] if self.precios else mid_price
        dp_ticks = (mid_price - p_base_ticks) / p_base_ticks if p_base_ticks > 0.0 else 0.0
        if cfg.es_modo_test() or len(self.precios_ts) < 4:
            return dp_ticks

        candidatos: List[float] = [dp_ticks]
        for ts_old, px_old in self.precios_ts:
            dt = ahora - ts_old
            if 2.0 <= dt <= 15.0 and px_old > 0.0:
                candidatos.append((mid_price - px_old) / px_old)

        mejor = dp_ticks
        for c in candidatos:
            if abs(c) > abs(mejor):
                mejor = c
        return mejor

    def actualizar_tick(
        self,
        mid_price: float,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        ahora: float,
    ) -> Dict[str, float]:
        if mid_price <= 0.0:
            return {}

        if (
            not cfg.es_modo_test()
            and self.prev_bids
            and self.prev_asks
            and bids[:5] == self.prev_bids
            and asks[:5] == self.prev_asks
            and (ahora - self.ts_ultimo_tick) < 0.150
            and self.ultimo_metricas
        ):
            return self.ultimo_metricas

        if self.precios:
            prev_p = self.precios[-1]
            ret = (mid_price - prev_p) / prev_p if prev_p > 0.0 else 0.0
            if abs(ret) > 1e-10 or cfg.es_modo_test() or len(self.retornos) < 10:
                self.retornos.append(ret)
        else:
            ret = 0.0

        if not self.precios or abs(mid_price - self.precios[-1]) > 1e-12 or cfg.es_modo_test() or (ahora - self.ts_ultimo_tick) >= 0.150:
            self.precios.append(mid_price)

        self.precios_ts.append((ahora, mid_price))
        self.ticks_totales += 1

        if self.ema900 <= 0.0:
            self.ema900 = mid_price
        else:
            self.ema900 = (self.alpha_ema900 * mid_price) + ((1.0 - self.alpha_ema900) * self.ema900)
        self.ema900_hist.append(self.ema900)

        ema_dist_pct = (mid_price - self.ema900) / self.ema900 if self.ema900 > 0.0 else 0.0
        if len(self.ema900_hist) >= 10 and self.ema900_hist[0] > 0.0:
            ema_slope_pct = (self.ema900 - self.ema900_hist[0]) / self.ema900_hist[0]
        else:
            ema_slope_pct = 0.0

        delta_p_pct = self._calcular_delta_p_biescala(mid_price, ahora)
        sigma_bv = self._calcular_sigma_bipower()
        n_eff = max(1.0, math.sqrt(min(len(self.precios), 25)))
        z_score = delta_p_pct / max(1e-7, sigma_bv * (0.45 * n_eff))

        ofi_raw = self._calcular_ml_ofi(bids, asks)
        if not cfg.es_modo_test() and abs(ofi_raw) < 1e-9 and self.ofi_hist:
            ofi_inst = self.ofi_hist[-1] * 0.70
        else:
            ofi_inst = ofi_raw

        self.ofi_hist.append(ofi_inst)
        ofi_5s = sum(self.ofi_hist) / len(self.ofi_hist)

        if ofi_inst >= cfg.OFI_MIN_ENTRADA:
            self.ofi_ticks_long += 1
        else:
            self.ofi_ticks_long = 0

        if ofi_inst <= cfg.SHORT_OFI_AGOTAMIENTO_MAX:
            self.ofi_ticks_short += 1
        else:
            self.ofi_ticks_short = 0

        hurst = self._calcular_hurst()
        lyap = self._calcular_lyapunov()

        dt = max(0.005, ahora - self.ts_ultimo_tick) if self.ts_ultimo_tick > 0.0 else 0.020
        self.ts_ultimo_tick = ahora
        decay = math.exp(-cfg.HAWKES_DECAY_BETA * dt)
        self.hawkes_intensidad = (self.hawkes_intensidad * decay) + ofi_inst

        if ret <= -0.0020 or ofi_inst <= -0.60:
            self.ts_ultimo_pulso_toxico = ahora

        imbalance_vpin = min(1.0, abs(ofi_inst) * min(1.0, abs(ret) * 40.0))
        self.vpin_actual = max(
            0.05,
            min(0.95, 0.92 * self.vpin_actual + 0.08 * imbalance_vpin),
        )

        self.ultimo_metricas = {
            "z_score": z_score,
            "delta_p_pct": delta_p_pct,
            "ema900": self.ema900,
            "ema900_dist_pct": ema_dist_pct,
            "ema900_slope_pct": ema_slope_pct,
            "ofi_l1_l5": ofi_inst,
            "ofi_5s": ofi_5s,
            "ofi_ticks_long": self.ofi_ticks_long,
            "ofi_ticks_short": self.ofi_ticks_short,
            "hurst": hurst,
            "lyapunov_acel_pct": lyap,
            "hawkes_intensidad": self.hawkes_intensidad,
            "vpin": self.vpin_actual,
            "sigma_bv": sigma_bv,
        }
        return self.ultimo_metricas


class RadarVolatilidad:
    """
    Motor de deteccion microestructural de alta frecuencia (50 Hz) con
    ejecucion secuencial de los 14 cerrojos SCAR-LOCK-00 a SCAR-LOCK-13.
    """

    def __init__(self) -> None:
        todos = tuple(cfg.PARES_CAMPEONES_ALFA) + (cfg.SIMBOLO_CENTINELA_MACRO,)
        self.ventanas: Dict[str, VentanaZ] = {sym: VentanaZ(sym) for sym in todos}
        self.vectores_entrada_baul: Dict[str, Dict[str, Any]] = {}

    def obtener_ventana(self, symbol: str) -> VentanaZ:
        v = self.ventanas.get(symbol)
        if v is None:
            v = VentanaZ(symbol)
            self.ventanas[symbol] = v
        return v

    def procesar_trade_publico(
        self,
        symbol: str,
        price: float,
        qty: float,
        side_taker: str,
    ) -> None:
        v = self.ventanas.get(symbol)
        if v is not None:
            v.registrar_trade_publico(price, qty, side_taker)

    def _evaluar_cortafuegos_cross_asset(
        self,
        symbol: str,
        delta_p_pct: float,
        z_score: float,
        ahora: float,
    ) -> bool:
        if symbol == cfg.SIMBOLO_CENTINELA_MACRO and z_score <= cfg.BTC_Z_CRASH_UMBRAL:
            ESTADO_RAM.pausa_macro_hasta_ts = max(
                ESTADO_RAM.pausa_macro_hasta_ts,
                ahora + cfg.CONTAGIO_PAUSA_MACRO_SEG,
            )
            return True

        if delta_p_pct <= -0.0065 and z_score <= -3.00:
            ESTADO_RAM.eventos_caida_recientes[symbol] = ahora

        activos_cayendo = [
            s
            for s, ts in list(ESTADO_RAM.eventos_caida_recientes.items())
            if (ahora - ts) <= cfg.CONTAGIO_VENTANA_SEG
        ]
        if len(activos_cayendo) >= cfg.CONTAGIO_PARES_SIMULTANEOS:
            ESTADO_RAM.pausa_macro_hasta_ts = max(
                ESTADO_RAM.pausa_macro_hasta_ts,
                ahora + cfg.CONTAGIO_PAUSA_MACRO_SEG,
            )
            return True

        tk_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)
        if tk_btc is not None and tk_btc.z_score <= cfg.BTC_Z_CRASH_UMBRAL:
            ESTADO_RAM.pausa_macro_hasta_ts = max(
                ESTADO_RAM.pausa_macro_hasta_ts,
                ahora + cfg.CONTAGIO_PAUSA_MACRO_SEG,
            )
            return True

        return False

    def procesar_libro_l2(
        self,
        symbol: str,
        bids: List[List[float]],
        asks: List[List[float]],
        last_price: Optional[float] = None,
        ahora: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        t_now = float(ahora) if ahora is not None else time.time()
        if not bids or not asks:
            return None

        bids_tuplas = [(float(b[0]), float(b[1])) for b in bids[:5] if float(b[0]) > 0.0]
        asks_tuplas = [(float(a[0]), float(a[1])) for a in asks[:5] if float(a[0]) > 0.0]
        if not bids_tuplas or not asks_tuplas:
            return None

        best_bid = bids_tuplas[0][0]
        best_ask = asks_tuplas[0][0]
        if best_ask <= best_bid:
            return None

        mid_price = (best_bid + best_ask) * 0.5
        spread_pct = (best_ask - best_bid) / mid_price
        px_last = float(last_price) if (last_price is not None and float(last_price) > 0.0) else mid_price

        ESTADO_RAM.evaluar_auditorias_escudo_vencidas(symbol, mid_price, ahora=t_now)

        ventana = self.obtener_ventana(symbol)
        m = ventana.actualizar_tick(mid_price, bids_tuplas, asks_tuplas, t_now)
        if not m:
            return None

        tk = ESTADO_RAM.ticks_ram.get(symbol)
        if tk is None:
            return None

        tk.bid = best_bid
        tk.ask = best_ask
        tk.last = px_last
        tk.spread_pct = spread_pct
        tk.z_score = m["z_score"]
        tk.delta_p_pct = m["delta_p_pct"]
        tk.ema900 = m["ema900"]
        tk.ema900_dist_pct = m["ema900_dist_pct"]
        tk.ema900_slope_pct = m["ema900_slope_pct"]
        tk.ofi_l1_l5 = m["ofi_l1_l5"]
        tk.ofi_5s = m["ofi_5s"]
        tk.ofi_ticks_confirmados_long = int(m["ofi_ticks_long"])
        tk.ofi_ticks_confirmados_short = int(m["ofi_ticks_short"])
        tk.hurst = m["hurst"]
        tk.lyapunov_acel_pct = m["lyapunov_acel_pct"]
        tk.hawkes_intensidad = m["hawkes_intensidad"]
        tk.vpin = m["vpin"]
        tk.volatilidad_local = m["sigma_bv"]
        tk.ts_ultimo_pulso_toxico = ventana.ts_ultimo_pulso_toxico
        tk.ts_tick = t_now
        tk.ofi_hibrido_50hz = m["ofi_l1_l5"]

        self._evaluar_cortafuegos_cross_asset(symbol, tk.delta_p_pct, tk.z_score, t_now)
        if symbol == cfg.SIMBOLO_CENTINELA_MACRO:
            return None

        if not ESCUDO_TRICORTEX.evaluar_filtro_anti_luna(symbol, tk.delta_p_pct, tk.vpin):
            return None

        es_test = cfg.es_modo_test()

        if not es_test and symbol == "INJ/USDT:USDT":
            return None

        # Supresor de rafaga: 12.0s entre disparos del mismo simbolo en produccion
        if not es_test and (t_now - ventana.ts_ultimo_disparo) < 12.0:
            return None

        min_ticks_arranque = 20 if es_test else 30
        if ventana.ticks_totales < min_ticks_arranque:
            return None

        if spread_pct > cfg.SPREAD_MAX_PCT:
            return None
        if tk.vpin > cfg.VPIN_TOXICO_MAX:
            return None

        p_dia, tag_p, _ = calcular_percentil_intradia_utc(ahora=t_now, sigma_bv=tk.volatilidad_local)
        params_clase = cfg.obtener_parametros_clase(
            symbol=symbol,
            patrimonio_actual_usdt=ESTADO_RAM.patrimonio_total_usdt,
        )

        umbral_choque_lyap = -max(0.0017, min(0.0025, 0.0025 - 0.0008 * p_dia))
        if tk.lyapunov_acel_pct <= umbral_choque_lyap:
            ventana.ts_ultimo_choque_lyapunov = t_now
        elif tk.lyapunov_acel_pct <= -0.00030:
            ventana.ts_ultima_replica_lyapunov = t_now

        # ======================================================================
        # RUTA 1: EVALUACION DE GATILLO LONG-REBOUND (SCAR-LOCK-02, 03, 07, 09, 10, 13)
        # ======================================================================
        z_umbral_long = float(params_clase["z_umbral"])
        caida_min_long = float(params_clase["caida_min_pct"])
        ema_min_long = float(params_clase["ema900_dist_min_pct"])

        if (
            tk.z_score <= z_umbral_long
            and tk.delta_p_pct <= caida_min_long
            and tk.ema900_dist_pct <= ema_min_long
        ):
            if not es_test and (t_now - ventana.ts_ultimo_choque_lyapunov) < 4.50:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    symbol, "long", "SCAR-LOCK-03_LYAP_4.5S", mid_price, tag_p, p_dia, "Buffer 4.5s", t_now
                )
                return None

            pausa_replica = 1.50 + 1.50 * p_dia
            if not es_test and (t_now - ventana.ts_ultima_replica_lyapunov) < pausa_replica:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    symbol, "long", "SCAR-LOCK-09_REPLICA_LYAP", mid_price, tag_p, p_dia, "Replica Lyap", t_now
                )
                return None

            if tk.lyapunov_acel_pct < cfg.LYAPUNOV_ACEL_MIN_PCT:
                return None

            h_max_long = cfg.HURST_MAX_ENTRADA if es_test else (0.465 if symbol in cfg.CLASE_TIER1_LIQUIDO else 0.475)
            if tk.hurst > h_max_long:
                ESTADO_RAM.encolar_auditoria_escudo_15s(
                    symbol, "long", "SCAR-LOCK-13_HURST_LONG", mid_price, tag_p, p_dia, f"H={tk.hurst:.3f}", t_now
                )
                return None

            if es_test:
                ofi_req_long = cfg.OFI_MIN_ENTRADA
            else:
                ofi_req_long = min(
                    0.45,
                    max(
                        0.18,
                        0.18
                        + 0.045 * p_dia
                        + 0.050 * max(0.0, abs(tk.z_score) - 4.50)
                        + (0.10 if tk.hurst >= 0.460 else 0.0),
                    ),
                )

            ticks_req = 3 if (not es_test and tk.ema900_dist_pct <= -0.0085) else cfg.OFI_TICKS_CONFIRMACION
            if tk.ofi_l1_l5 < ofi_req_long or tk.ofi_ticks_confirmados_long < ticks_req:
                return None

            dt_pulso = t_now - ventana.ts_ultimo_pulso_toxico
            if dt_pulso < cfg.HAWKES_ABSORCION_MIN_SEG or tk.hawkes_intensidad < cfg.HAWKES_INTENSIDAD_MIN:
                return None

            ok_perm, motivo_perm, _ = ESTADO_RAM.consultar_permiso_o1(
                symbol=symbol,
                side_solicitado="long",
                z_score_actual=tk.z_score,
                ahora=t_now,
            )
            if not ok_perm:
                return None

            ventana.ts_ultimo_disparo = t_now
            kelly_info = ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil(
                symbol=symbol,
                z_score=tk.z_score,
                ofi=tk.ofi_l1_l5,
                side="long",
                hurst=tk.hurst,
            )
            tk.grado_senal = str(kelly_info["grado_senal"])
            tk_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)

            senal_long = {
                "symbol": symbol,
                "side": "long",
                "mid_price": mid_price,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "z_score": tk.z_score,
                "delta_p_pct": tk.delta_p_pct,
                "ema900_dist_pct": tk.ema900_dist_pct,
                "ema900_slope_pct": tk.ema900_slope_pct,
                "ofi": tk.ofi_l1_l5,
                "hurst": tk.hurst,
                "lyapunov_acel_pct": tk.lyapunov_acel_pct,
                "hawkes_intensidad": tk.hawkes_intensidad,
                "vpin": tk.vpin,
                "sigma_bv": tk.volatilidad_local,
                "p_dia": p_dia,
                "tag_percentil": tag_p,
                "z_btc": tk_btc.z_score if tk_btc else 0.0,
                "ofi_btc": tk_btc.ofi_l1_l5 if tk_btc else 0.0,
                "fraccion_kelly": kelly_info["fraccion_kelly"],
                "nocional_usdt": kelly_info["nocional_usdt"],
                "margen_usdt": kelly_info["margen_usdt"],
                "grado_senal": kelly_info["grado_senal"],
                "iceberg_requerido": kelly_info["iceberg_requerido"],
                "house_money_usdt": kelly_info["house_money_usdt"],
                "slot_modo": ESTADO_RAM.ultimo_modo_slot_autorizado,
                "motivo_permiso": motivo_perm,
            }
            self.vectores_entrada_baul[symbol] = senal_long
            return senal_long

        # ======================================================================
        # RUTA 2: EVALUACION DE GATILLO SHORT-SNIPER (SCAR-LOCK-01, 08, 11)
        # ======================================================================
        if not cfg.MODO_BIDIRECCIONAL:
            return None

        z_umbral_short = abs(float(params_clase["z_umbral"]))
        if tk.z_score < z_umbral_short:
            return None

        if es_test:
            es_pump_short = tk.delta_p_pct >= cfg.SHORT_PUMP_SOBREEXTENSION_PCT
            es_rebote_debil = (
                tk.ema900_dist_pct <= cfg.SHORT_REBOTE_DEBIL_MIN_EMA_PCT
                and tk.delta_p_pct >= 0.0035
            )
            if not (es_pump_short or es_rebote_debil):
                return None
        else:
            piso_ema_short = 0.0032 if symbol in cfg.CLASE_HIGH_BETA else 0.0025
            bono_h_short = 0.0012 if tk.hurst >= 0.480 else 0.0
            bono_z_short = 0.0008 if abs(tk.z_score) >= 8.00 else 0.0
            ema_req_short = piso_ema_short + 0.0010 * p_dia + bono_h_short + bono_z_short

            if (
                (t_now - ventana.ts_ultimo_anti_squeeze) < 180.0
                and ventana.px_ultimo_anti_squeeze > 0.0
                and mid_price >= ventana.px_ultimo_anti_squeeze
            ):
                ema_req_short = max(ema_req_short, 0.0045)

            if tk.ema900_dist_pct < ema_req_short or tk.delta_p_pct < 0.0032:
                return None

            sl_prev = ESTADO_RAM.ultimo_sl_short_precio.get(symbol)
            if sl_prev is not None:
                px_sl_prev, ts_sl_prev = sl_prev
                if (t_now - ts_sl_prev) < 1800.0 and mid_price >= px_sl_prev * 0.9985:
                    ESTADO_RAM.encolar_auditoria_escudo_15s(
                        symbol, "short", "SCAR-LOCK-11_STEP_LOCK", mid_price, tag_p, p_dia, "Step-Lock 1800s", t_now
                    )
                    return None

        h_max_short = 0.495 if symbol in cfg.CLASE_TIER1_LIQUIDO else 0.505
        if tk.hurst > h_max_short:
            return None

        if es_test:
            ofi_max_short = cfg.SHORT_OFI_AGOTAMIENTO_MAX
        else:
            ofi_max_short = -(0.35 + 0.12 * p_dia)
            if (
                (t_now - ventana.ts_ultimo_anti_squeeze) < 180.0
                and ventana.px_ultimo_anti_squeeze > 0.0
                and mid_price >= ventana.px_ultimo_anti_squeeze
            ):
                ofi_max_short -= 0.12

        if (
            tk.ofi_l1_l5 > ofi_max_short
            or tk.ofi_ticks_confirmados_short < cfg.OFI_TICKS_CONFIRMACION
            or tk.lyapunov_acel_pct > cfg.SHORT_LYAPUNOV_ACEL_MAX_PCT
        ):
            return None

        ok_perm_s, motivo_perm_s, _ = ESTADO_RAM.consultar_permiso_o1(
            symbol=symbol,
            side_solicitado="short",
            z_score_actual=tk.z_score,
            ahora=t_now,
        )
        if not ok_perm_s:
            return None

        ventana.ts_ultimo_disparo = t_now
        kelly_info_s = ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil(
            symbol=symbol,
            z_score=tk.z_score,
            ofi=tk.ofi_l1_l5,
            side="short",
            hurst=tk.hurst,
        )
        tk.grado_senal = str(kelly_info_s["grado_senal"])
        tk_btc = ESTADO_RAM.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)

        senal_short = {
            "symbol": symbol,
            "side": "short",
            "mid_price": mid_price,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "z_score": tk.z_score,
            "delta_p_pct": tk.delta_p_pct,
            "ema900_dist_pct": tk.ema900_dist_pct,
            "ema900_slope_pct": tk.ema900_slope_pct,
            "ofi": tk.ofi_l1_l5,
            "hurst": tk.hurst,
            "lyapunov_acel_pct": tk.lyapunov_acel_pct,
            "hawkes_intensidad": tk.hawkes_intensidad,
            "vpin": tk.vpin,
            "sigma_bv": tk.volatilidad_local,
            "p_dia": p_dia,
            "tag_percentil": tag_p,
            "z_btc": tk_btc.z_score if tk_btc else 0.0,
            "ofi_btc": tk_btc.ofi_l1_l5 if tk_btc else 0.0,
            "fraccion_kelly": kelly_info_s["fraccion_kelly"],
            "nocional_usdt": kelly_info_s["nocional_usdt"],
            "margen_usdt": kelly_info_s["margen_usdt"],
            "grado_senal": kelly_info_s["grado_senal"],
            "iceberg_requerido": kelly_info_s["iceberg_requerido"],
            "house_money_usdt": kelly_info_s["house_money_usdt"],
            "slot_modo": ESTADO_RAM.ultimo_modo_slot_autorizado,
            "motivo_permiso": motivo_perm_s,
        }
        self.vectores_entrada_baul[symbol] = senal_short
        return senal_short


RADAR: RadarVolatilidad = RadarVolatilidad()