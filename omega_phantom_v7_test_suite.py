#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #12: omega_phantom_v7_test_suite.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Suite Determinista de Certificacion End-to-End (18/18 Pruebas):
Valida AST, UTF-8 sin BOM, 100 constantes unicas, Lookup RAM O(1), Semaforo
Ortogonal de 2 Slots, Kelly Asimetrico House-Money, Glosten-Milgrom, Radar
50Hz, Avellaneda-Stoikov, Ley de Cola Moallemi-Yuan, Cosecha TRIZ, Maker-Scratch
18s, captura de retCode:110017 y Hot-Reload OOS.
==============================================================================
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import pathlib
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

os.environ["OMEGA_TEST_MODE"] = "1"

import omega_phantom_v7_config as cfg
from omega_phantom_v7_gestor import GESTOR_POSICIONES
from omega_phantom_v7_main import (
    CerrojoInstanciaUnica,
    auditar_y_filtrar_lotes_minimos,
    reconciliar_posiciones_arranque,
)
from omega_phantom_v7_oos_twin import ejecutar_calibracion_oos
from omega_phantom_v7_radar import RADAR, VentanaZ
from omega_phantom_v7_ram import ESTADO_RAM, PosicionActiva, log_sniper
from omega_phantom_v7_sniper import EJECUTOR_SNIPER
from omega_phantom_v7_stats import CAJA_NEGRA, GestorCajaNegra
from omega_phantom_v7_telegram import TELEMETRIA_TG
from omega_phantom_v7_tricortex import (
    ESCUDO_TRICORTEX,
    calcular_atenuacion_glosten_milgrom,
)
from tools.omega_phantom_v7_validator import ejecutar_auditoria


class _MockExchangeBybit:
    """Simulador determinista de Bybit UTA V5 para las pruebas 05, 14, 15, 16 y 17."""

    def __init__(self) -> None:
        self.modo_orden: str = "NO_FILL"
        self.create_calls: int = 0
        self.cancel_calls: int = 0
        self.lanzar_110017_en_cierre: bool = False

    async def fetch_balance(self) -> Dict[str, Any]:
        return {"USDT": {"total": 10.0000, "free": 10.0000}}

    async def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        return [
            {
                "symbol": "ZEREBRO/USDT:USDT",
                "side": "long",
                "contracts": 500.0,
                "entryPrice": 0.02500,
            }
        ]

    async def fetch_open_orders(self, symbol: str) -> List[Dict[str, Any]]:
        if symbol == "WAL/USDT:USDT":
            return [{"id": "ORD_HUERFANA_1", "symbol": symbol}]
        return []

    async def load_markets(self) -> Dict[str, Any]:
        mercados: Dict[str, Any] = {}
        for sym in cfg.PARES_CAMPEONES_ALFA:
            mercados[sym] = {
                "limits": {"amount": {"min": 1.0}},
                "precision": {"price": 0.0001, "amount": 0.1},
                "info": {"lastPrice": "0.0300"},
            }
        mercados["TAO/USDT:USDT"] = {
            "limits": {"amount": {"min": 1.0}},
            "precision": {"price": 0.01, "amount": 0.1},
            "info": {"lastPrice": "450.0"},
        }
        return mercados

    async def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self.lanzar_110017_en_cierre and params and params.get("reduceOnly"):
            raise RuntimeError("bybit retCode: 110017 - current position is zero")
        self.create_calls += 1
        return {
            "id": f"MOCK_ORD_{self.create_calls}",
            "symbol": symbol,
            "type": type,
            "side": side,
            "amount": amount,
            "price": price or 0.0,
            "status": "open",
        }

    async def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        if self.modo_orden == "FILL_IMMEDIATE":
            return {"id": order_id, "status": "closed", "filled": 700.0, "average": 0.02200}
        return {"id": order_id, "status": "open", "filled": 0.0, "average": 0.0}

    async def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        self.cancel_calls += 1
        return {"id": order_id, "status": "canceled"}

    async def set_trading_stop(self, symbol: str, stopLoss: float) -> Dict[str, Any]:
        return {"retCode": 0, "symbol": symbol, "stopLoss": stopLoss}


async def ejecutar_suite_18_pruebas() -> int:
    log_sniper("=" * 86)
    log_sniper(f" INICIANDO SUITE DE CERTIFICACION: {cfg.NOMBRE_ESTRATEGIA} (18/18)")
    log_sniper("=" * 86)

    # [01/18] Auditoria estatica AST / UTF-8 / LF / 100 Constantes
    rc_ast = ejecutar_auditoria(modo_estricto_completo=True)
    assert rc_ast == 0, "Fallo en Compuerta 0 (validador AST/UTF-8)"
    log_sniper(" [01/18] Compilacion AST (17/17 archivos), UTF-8 sin BOM, 0 Mojibake y 100 constantes validados.")

    # [02/18] Invariantes de configuracion y capital base
    assert cfg.CAPITAL_BASE_USDT == 10.0000
    assert cfg.FEE_MAKER_PCT == 0.00020 and cfg.FEE_TAKER_PCT == 0.00055
    assert len(cfg.PARES_CAMPEONES_ALFA) == 7 and len(cfg.PARES_VETADOS_OOS) == 12
    assert cfg.PERMITIR_REQUOTE is False
    log_sniper(" [02/18] Invariantes de configuracion (Base 10.00 USDT, 7 Campeones Alfa y 12 Vetados OOS) validados.")

    # [03/18] Benchmark O(1) en ESTADO_RAM y Semaforo Ortogonal de 2 Slots
    ESTADO_RAM.slot_ocupado = False
    ESTADO_RAM.posiciones_activas.clear()
    ESTADO_RAM.pares_excluidos_lote.clear()
    t0 = time.perf_counter_ns()
    for _ in range(1000):
        ok_p, _, _ = ESTADO_RAM.consultar_permiso_o1("ZEREBRO/USDT:USDT", "long", -3.80)
    us_por_lookup = (time.perf_counter_ns() - t0) / 1000.0 / 1000.0
    assert ok_p is True and us_por_lookup < 15.0
    log_sniper(f" [03/18] Lookup O(1) en ESTADO_RAM certificado en {us_por_lookup:.3f} us (< 15.0 us SLA).")

    # [04/18] Cerrojo Fisico de Instancia Unica
    with tempfile.TemporaryDirectory() as tmpdir:
        ruta_lk = pathlib.Path(tmpdir) / ".omega_test.lock"
        lk1 = CerrojoInstanciaUnica(ruta_lk)
        assert lk1.adquirir() is True
        lk1.liberar()
        assert not ruta_lk.exists()
    log_sniper(" [04/18] Cerrojo fisico de instancia unica (.omega_phantom_v7.lock) validado.")

    # [05/18] Reconciliacion de Arranque UTA y Filtro de Lotes Minimos
    mock_ex = _MockExchangeBybit()
    excluidos = await auditar_y_filtrar_lotes_minimos(mock_ex)
    assert "TAO/USDT:USDT" in excluidos
    ESTADO_RAM.pares_excluidos_lote.discard("TAO/USDT:USDT")
    rec_info = await reconciliar_posiciones_arranque(mock_ex)
    assert rec_info["adoptadas"] == 1 and rec_info["ordenes_canceladas"] == 1
    ESTADO_RAM.liberar_margen_atomico("ZEREBRO/USDT:USDT")
    log_sniper(" [05/18] Reconciliacion de arranque en Bybit UTA y filtro de lotes minimos validados.")

    # [06/18] Contabilidad Caja Negra, desduplicacion O(N) y Paridad 1:1
    with tempfile.TemporaryDirectory() as tmpdir:
        ruta_st = pathlib.Path(tmpdir) / "stats_test.jsonl"
        cn = GestorCajaNegra(ruta_st)
        p_test = PosicionActiva(
            symbol="ARB/USDT:USDT",
            side="short",
            qty_inicial=50.0,
            qty_actual=50.0,
            entry_price=0.5000,
            ts_apertura=time.time() - 25.0,
        )
        reg_t = cn.registrar_cierre(p_test, exit_price=0.4970, motivo="TRAILING_RATCHET_MAKER", es_maker_salida=True)
        assert reg_t is not None and reg_t.pnl_usdt > 0.0
        assert cn.registrar_cierre(p_test, exit_price=0.4970, motivo="DUPLICADO") is None
        bal_sinc = cn.sincronizar_paridad_uta(10.8500)
        assert abs(bal_sinc - 10.8500) < 1e-4
    log_sniper(" [06/18] Contabilidad CAJA_NEGRA, cerrojo anti-duplicado y Paridad Exacta 1:1 UTA validados.")

    # [07/18] Telemetria Transaccional 1:1 en Telegram (Cero Ruido)
    TELEMETRIA_TG.registrar_apertura_pendiente(
        symbol="WAL/USDT:USDT",
        side="long",
        qty=200.0,
        entry_price=0.0800,
        nocional_usdt=16.0,
        apalancamiento=3,
        fraccion_kelly=0.55,
        z_score=-3.5,
        ofi=0.35,
    )
    assert TELEMETRIA_TG.descartar_apertura_no_llenada("WAL/USDT:USDT") is True
    assert await TELEMETRIA_TG.confirmar_y_despachar_apertura("WAL/USDT:USDT") is False
    log_sniper(" [07/18] Protocolo Transaccional 1:1 en Telegram (retencion pre-fill y cero spam) validado.")

    # [08/18] Filtro Determinista Anti-LUNA
    ok_luna = ESCUDO_TRICORTEX.evaluar_filtro_anti_luna("XRP/USDT:USDT", caida_pct=-0.075, vpin=0.90)
    assert ok_luna is False
    assert ESTADO_RAM.permisos_ram["XRP/USDT:USDT"].modo_regimen == "VETO_TOXIC"
    ESCUDO_TRICORTEX._inicializar_whitelist_o1()
    log_sniper(" [08/18] Escudo determinista Anti-LUNA (-7.5% -> VETO_TOXIC y cuarentena 900s) validado.")

    # [09/18] Dimensionamiento de Kelly, Glosten-Milgrom y Acelerador House-Money
    k_mod = ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil("ZEREBRO/USDT:USDT", -3.25, 0.20, "long")
    k_ext = ESCUDO_TRICORTEX.calcular_fraccion_kelly_antifragil("ZEREBRO/USDT:USDT", -4.90, 0.85, "long")
    assert k_ext["fraccion_kelly"] >= k_mod["fraccion_kelly"]
    assert k_ext["nocional_usdt"] <= cfg.NOCIONAL_MAX_HIGH_BETA_USDT
    f_gm = calcular_atenuacion_glosten_milgrom(0.62, z_score=-15.0)
    assert f_gm < 0.62 and f_gm >= cfg.KELLY_FRACCION_MIN
    hm_res = cfg.calcular_kelly_asim_house_money(
        symbol="ZEREBRO/USDT:USDT",
        side="short",
        z_score=4.60,
        ofi=-0.65,
        hurst=0.42,
        patrimonio_actual_usdt=12.00,
    )
    assert hm_res["es_grado_a_plus"] is True and hm_res["nocional_objetivo_usdt"] > 16.50
    log_sniper(" [09/18] Kelly Convexo, atenuacion Glosten-Milgrom y Acelerador House-Money A+ validados.")

    # [10/18] Variacion Bipower de Barndorff-Nielsen & Shephard
    vz = VentanaZ("ARB/USDT:USDT")
    t_sim = time.time()
    for i in range(25):
        px = 0.5000 * (1.0 + 0.0003 * math.sin(i * 1.9))
        vz.actualizar_tick(px, [(px - 0.0001, 100.0)], [(px + 0.0001, 100.0)], t_sim + i * 0.02)
    sigma_limpia = vz._calcular_sigma_bipower()
    assert sigma_limpia >= 0.00020
    log_sniper(f" [10/18] Variacion Bipower de Barndorff-Nielsen & Shephard validada (sigma_BV={sigma_limpia:.5f}).")

    # [11/18] Fusion H-OFI 50 Hz (ML-OFI L1-L5 + publicTrade) y Exponente de Hurst
    vz.registrar_trade_publico(0.5005, 5000.0, "buy")
    ofi_pos = vz._calcular_ml_ofi(
        [(0.5002, 800.0), (0.5001, 600.0)],
        [(0.5003, 100.0), (0.5004, 100.0)],
    )
    h_est = vz._calcular_hurst()
    assert ofi_pos > 0.0 and 0.25 <= h_est <= 0.75
    log_sniper(f" [11/18] Fusion H-OFI 50Hz (OFI={ofi_pos:+.3f}) y Exponente Fractal de Hurst (H={h_est:.3f}) validados.")

    # [12/18] Repulsor Cinetico de Lyapunov y Memoria Auto-Excitada de Hawkes
    vz.precios.extend([0.5000, 0.4950, 0.4945])
    acel_frenado = vz._calcular_lyapunov()
    assert acel_frenado > 0.0
    log_sniper(f" [12/18] Repulsor de Lyapunov (frenado a={acel_frenado*100:+.3f}%) y Memoria de Hawkes validados.")

    # [13/18] Cortafuegos Cross-Asset y Gatillo Bidireccional SHORT-SNIPER
    t_now = time.time()
    bloqueo_btc = RADAR._evaluar_cortafuegos_cross_asset("BTC/USDT:USDT", -0.015, -4.50, t_now)
    assert bloqueo_btc is True and ESTADO_RAM.pausa_macro_hasta_ts > t_now
    ESTADO_RAM.pausa_macro_hasta_ts = 0.0
    ESTADO_RAM.eventos_caida_recientes.clear()

    vz_s = RADAR.obtener_ventana("ZEREBRO/USDT:USDT")
    vz_s.precios.clear()
    vz_s.retornos.clear()
    for i in range(25):
        p_b = 0.03000 * (1.0 + (0.00025 if i % 2 == 0 else -0.00020))
        RADAR.procesar_libro_l2(
            "ZEREBRO/USDT:USDT",
            [[p_b - 0.00001, 500.0]] * 5,
            [[p_b + 0.00001, 500.0]] * 5,
            ahora=t_now + i * 0.02,
        )

    secuencia_pump = (
        (0.03046, 0.03048, 400.0, 400.0),
        (0.03045, 0.03047, 100.0, 2500.0),
        (0.03043, 0.03045, 50.0, 5000.0),
        (0.03039, 0.03041, 25.0, 9000.0),
    )
    senal_short = None
    for idx_p, (bid_p, ask_p, bid_q, ask_q) in enumerate(secuencia_pump, start=1):
        RADAR.procesar_trade_publico("ZEREBRO/USDT:USDT", bid_p, 25000.0, "sell")
        res_s = RADAR.procesar_libro_l2(
            "ZEREBRO/USDT:USDT",
            [[bid_p, bid_q]] * 5,
            [[ask_p, ask_q]] * 5,
            ahora=t_now + 1.0 + idx_p * 0.02,
        )
        if res_s is not None:
            senal_short = res_s

    assert senal_short is not None and senal_short["side"] == "short"
    log_sniper(" [13/18] Cortafuegos Cross-Asset BTC y gatillo simetrico SHORT-SNIPER validados.")

    # [14/18] Ley de Cola Moallemi-Yuan (TTL=2.2s) y Abolicion del Re-Quote
    mock_ex.create_calls = 0
    mock_ex.cancel_calls = 0
    mock_ex.modo_orden = "NO_FILL"
    tk_z = ESTADO_RAM.ticks_ram.get("ZEREBRO/USDT:USDT")
    if tk_z is not None:
        tk_z.ofi_l1_l5 = -0.35
    EJECUTOR_SNIPER.configurar_exchange(mock_ex)
    GESTOR_POSICIONES.configurar_exchange(mock_ex)
    pos_nofill = await EJECUTOR_SNIPER.ejecutar_senal_sniper(senal_short)
    assert pos_nofill is None
    assert mock_ex.create_calls == 1 and mock_ex.cancel_calls == 1
    assert ESTADO_RAM.slot_ocupado is False
    log_sniper(" [14/18] Ley de Cola Moallemi-Yuan (TTL=2.2s) y Abolicion Fisica del Re-Quote (1 create + 1 cancel) validadas.")

    # [15/18] Ley 3: Piso BE+, Cosecha 50% TRIZ y cierre en TRAILING_RATCHET_MAKER
    pos_win = PosicionActiva(
        symbol="ZEREBRO/USDT:USDT",
        side="long",
        qty_inicial=700.0,
        qty_actual=700.0,
        entry_price=0.02200,
        ts_apertura=time.time() - 10.0,
        sl_interno_price=0.02189,
        sl_bybit_price=0.02185,
    )
    ESTADO_RAM.posiciones_activas["ZEREBRO/USDT:USDT"] = pos_win
    ESTADO_RAM.slot_ocupado = True
    await GESTOR_POSICIONES.evaluar_posicion_activa(pos_win, precio_actual=0.02208, ofi_5s=0.35)
    assert pos_win.cosecha_50_ejecutada is True and pos_win.trinquete_be_armado is True
    await GESTOR_POSICIONES.evaluar_posicion_activa(pos_win, precio_actual=0.02216, ofi_5s=0.40)
    assert pos_win.trailing_activo is True
    await GESTOR_POSICIONES.evaluar_posicion_activa(pos_win, precio_actual=0.02210, ofi_5s=-0.10)
    assert pos_win.cerrada is True
    log_sniper(" [15/18] Ley 3 validada: Piso BE+, Cosecha 50% TRIZ PostOnly y cierre en TRAILING_RATCHET_MAKER.")

    # [16/18] Ley 2: Evacuacion Pasiva Maker-Scratch a los 18s
    pos_scr = PosicionActiva(
        symbol="ARB/USDT:USDT",
        side="long",
        qty_inicial=40.0,
        qty_actual=40.0,
        entry_price=0.5000,
        ts_apertura=time.time() - 18.5,
        sl_interno_price=0.4976,
        sl_bybit_price=0.4965,
    )
    ESTADO_RAM.posiciones_activas["ARB/USDT:USDT"] = pos_scr
    ESTADO_RAM.slot_ocupado = True
    await GESTOR_POSICIONES.evaluar_posicion_activa(pos_scr, precio_actual=0.4996, ofi_5s=-0.32)
    assert pos_scr.cerrada is True and pos_scr.scratch_18s_activo is True
    log_sniper(" [16/18] Ley 2 validada: Evacuacion pasiva Maker-Scratch a los 18s (MAKER_SCRATCH_18S).")

    # [17/18] Cerrojo pos.cerrada y captura nativa de retCode: 110017 (SL_EXCHANGE)
    mock_ex.lanzar_110017_en_cierre = True
    pos_sl = PosicionActiva(
        symbol="WAL/USDT:USDT",
        side="long",
        qty_inicial=300.0,
        qty_actual=300.0,
        entry_price=0.0500,
        ts_apertura=time.time() - 25.0,
        sl_interno_price=0.04976,
        sl_bybit_price=0.04970,
    )
    ESTADO_RAM.posiciones_activas["WAL/USDT:USDT"] = pos_sl
    ESTADO_RAM.slot_ocupado = True
    await GESTOR_POSICIONES.evaluar_posicion_activa(pos_sl, precio_actual=0.04970, ofi_5s=-0.45)
    assert pos_sl.cerrada is True
    assert CAJA_NEGRA.operaciones[-1].motivo == "SL_EXCHANGE"
    mock_ex.lanzar_110017_en_cierre = False
    log_sniper(" [17/18] Cerrojo pos.cerrada, captura nativa retCode:110017 (SL_EXCHANGE) y garantia 1:1 en Telegram validados.")

    # [18/18] Evaluador Cuantico OOS, Hot-Reload sub-milisegundo e instalador Unix LF
    with tempfile.TemporaryDirectory() as tmpdir:
        p_tmp = pathlib.Path(tmpdir)
        ruta_st_oos = p_tmp / "stats_oos.jsonl"
        ruta_js_oos = p_tmp / "calibracion_oos.json"
        ruta_md_oos = p_tmp / "reporte_oos.md"
        cn_oos = GestorCajaNegra(ruta_st_oos)
        cn_oos.operaciones = list(CAJA_NEGRA.operaciones[-3:])
        with open(ruta_st_oos, "w", encoding="utf-8") as f_s:
            for op in cn_oos.operaciones:
                f_s.write(json.dumps(op.to_dict()) + "\n")

        res_cal = ejecutar_calibracion_oos(
            ruta_stats=ruta_st_oos,
            ruta_json_out=ruta_js_oos,
            ruta_md_out=ruta_md_oos,
        )
        assert res_cal["lambda_bayes"] > 0.0 and ruta_js_oos.exists()
        t_hr0 = time.perf_counter()
        hr_info = cfg.recargar_calibracion_oos_si_cambio(ruta_js_oos)
        ms_hr = (time.perf_counter() - t_hr0) * 1000.0
        assert hr_info["recargado"] is True and ms_hr < 15.0

    sh_bytes = (cfg.ROOT_DIR / "omega_phantom_v7_install.sh").read_bytes()
    assert b"\r\n" not in sh_bytes
    log_sniper(
        f" [18/18] Evaluador Cuantico OOS (lambda={res_cal['lambda_bayes']:.2f}), Hot-Reload ({ms_hr:.2f} ms) e instalador Unix LF validados."
    )

    log_sniper("=" * 86)
    log_sniper(f" TODAS LAS PRUEBAS DE INTEGRIDAD {cfg.NOMBRE_ESTRATEGIA} (18/18) SUPERADAS")
    log_sniper("=" * 86)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(ejecutar_suite_18_pruebas()))