#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #04: omega_phantom_v7_stats.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Motor Contable de Caja Negra (omega_phantom_v7_stats.jsonl):
  1. Desduplicacion automatica O(N) en el arranque.
  2. Contabilidad real de cosechas parciales verificadas en Bybit.
  3. Paridad Exacta 1:1 con el patrimonio real de Bybit UTA (SCAR-LOCK-04).
  4. Calculo de MAP, LVR, Velocidad Geometrica g* (Kelly-Shannon) y progreso
     hacia la meta del Desafio 48H (10.00 USDT -> 14.00 USDT).
  5. Escritura automatica de TRADE_COMPLETO en omega_phantom_v7_baul_ia.jsonl.
==============================================================================
"""
from __future__ import annotations

import json
import math
import pathlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import omega_phantom_v7_config as cfg
from omega_phantom_v7_ram import (
    ESTADO_RAM,
    PosicionActiva,
    RegistroOperacionCerrada,
    log_sniper,
    registrar_evento_baul_ia,
)


class GestorCajaNegra:
    """Motor de contabilidad forense y paridad 1:1 con Bybit UTA."""

    def __init__(self, ruta_jsonl: Optional[pathlib.Path] = None) -> None:
        self.ruta_jsonl: pathlib.Path = ruta_jsonl or (cfg.ROOT_DIR / cfg.ARCHIVO_STATS_JSONL)
        self.operaciones: List[RegistroOperacionCerrada] = []
        self.cosechas_parciales_count: int = 0
        self.pnl_cosechas_huérfanas_usdt: float = 0.0
        self.ajuste_paridad_uta_usdt: float = 0.0
        self.patrimonio_real_uta_usdt: float = cfg.CAPITAL_BASE_USDT
        self.cargar_y_auditar_historial()

    def cargar_y_auditar_historial(self) -> int:
        self.operaciones.clear()
        if not self.ruta_jsonl.exists():
            return 0

        vistos: set[str] = set()
        lineas_limpias: List[str] = []
        duplicados = 0

        try:
            for linea in self.ruta_jsonl.read_text(encoding="utf-8-sig").splitlines():
                linea_str = linea.strip()
                if not linea_str:
                    continue
                try:
                    d = json.loads(linea_str)
                except Exception:
                    continue

                clave = (
                    f"{d.get('timestamp', '')}|{d.get('symbol', '')}|"
                    f"{d.get('side', '')}|{round(float(d.get('entry_price', 0.0)), 6)}|"
                    f"{round(float(d.get('exit_price', 0.0)), 6)}"
                )
                if clave in vistos:
                    duplicados += 1
                    continue
                vistos.add(clave)
                lineas_limpias.append(json.dumps(d, ensure_ascii=False))

                reg = RegistroOperacionCerrada(
                    timestamp=str(d.get("timestamp", "")),
                    symbol=str(d.get("symbol", "")),
                    side=str(d.get("side", "long")),
                    z_score_entry=float(d["z_score_entry"]) if d.get("z_score_entry") is not None else 0.0,
                    ofi_entry=float(d["ofi_entry"]) if d.get("ofi_entry") is not None else 0.0,
                    hurst_entry=float(d["hurst_entry"]) if d.get("hurst_entry") is not None else 0.45,
                    pnl_percentage=float(d.get("pnl_percentage", 0.0)),
                    pnl_usdt=float(d.get("pnl_usdt", 0.0)),
                    entry_price=float(d.get("entry_price", 0.0)),
                    exit_price=float(d.get("exit_price", 0.0)),
                    qty=float(d.get("qty", 0.0)),
                    motivo=str(d.get("motivo", "UNKNOWN")),
                    hold_seg=float(d.get("hold_seg", 0.0)),
                    fees_usdt=float(d.get("fees_usdt", 0.0)),
                    map_usdt=float(d.get("map_usdt", 0.0)),
                    lvr_usdt=float(d.get("lvr_usdt", 0.0)),
                    cosecha_triz_50=bool(d.get("cosecha_triz_50", False)),
                )
                self.operaciones.append(reg)

            if duplicados > 0 and not cfg.es_modo_test():
                self.ruta_jsonl.write_text("\n".join(lineas_limpias) + "\n", encoding="utf-8")
        except Exception as exc:
            log_sniper(f"[CAJA NEGRA WARN] Error auditando historial: {exc}")

        self.cosechas_parciales_count = sum(1 for op in self.operaciones if op.cosecha_triz_50)
        return len(self.operaciones)

    def registrar_cosecha_parcial_en_vivo(self, pos: PosicionActiva, pnl_parcial_neto_usdt: float, fee_usdt: float) -> None:
        pos.pnl_realizado_parcial_usdt += float(pnl_parcial_neto_usdt)
        pos.fees_acumulados_usdt += float(fee_usdt)
        self.cosechas_parciales_count += 1

    def sincronizar_paridad_uta(self, balance_real_bybit_usdt: float) -> float:
        """
        Garantiza SCAR-LOCK-04 (Paridad Contable Exacta 1:1):
        Alinea el balance contable de la Caja Negra con el patrimonio real de Bybit UTA.
        """
        if balance_real_bybit_usdt <= 0.0:
            return self.obtener_balance_contable_usdt()
        self.patrimonio_real_uta_usdt = float(balance_real_bybit_usdt)
        pnl_trades = sum(op.pnl_usdt for op in self.operaciones)
        balance_crudo = cfg.CAPITAL_BASE_USDT + pnl_trades + self.pnl_cosechas_huérfanas_usdt
        self.ajuste_paridad_uta_usdt = round(self.patrimonio_real_uta_usdt - balance_crudo, 6)
        ESTADO_RAM.sincronizar_balance_uta(self.patrimonio_real_uta_usdt, self.patrimonio_real_uta_usdt)
        return self.obtener_balance_contable_usdt()

    def obtener_pnl_neto_total_usdt(self) -> float:
        pnl_trades = sum(op.pnl_usdt for op in self.operaciones)
        return round(pnl_trades + self.pnl_cosechas_huérfanas_usdt + self.ajuste_paridad_uta_usdt, 4)

    def obtener_balance_contable_usdt(self) -> float:
        return round(cfg.CAPITAL_BASE_USDT + self.obtener_pnl_neto_total_usdt(), 4)

    def registrar_cierre(
        self,
        pos: PosicionActiva,
        exit_price: float,
        motivo: str,
        es_maker_salida: bool = True,
        ahora: Optional[float] = None,
    ) -> Optional[RegistroOperacionCerrada]:
        if pos.cerrada:
            return None
        pos.cerrada = True

        t_now = ahora if ahora is not None else time.time()
        hold_seg = max(0.1, t_now - pos.ts_apertura)
        pnl_bruto_rem_pct = pos.calcular_pnl_bruto_pct(exit_price)
        nocional_rem_usdt = pos.qty_actual * pos.entry_price
        nocional_ini_usdt = pos.qty_inicial * pos.entry_price

        fee_entry_rem = nocional_rem_usdt * cfg.FEE_MAKER_PCT
        fee_exit_rem = nocional_rem_usdt * (cfg.FEE_MAKER_PCT if es_maker_salida else cfg.FEE_TAKER_PCT)
        fees_rem_usdt = fee_entry_rem + fee_exit_rem

        pnl_neto_rem_usdt = (nocional_rem_usdt * pnl_bruto_rem_pct) - fees_rem_usdt
        pnl_neto_total_usdt = round(pnl_neto_rem_usdt + pos.pnl_realizado_parcial_usdt, 4)
        fees_totales_usdt = round(fees_rem_usdt + pos.fees_acumulados_usdt, 4)

        pnl_pct_efectivo = (
            round((pnl_neto_total_usdt / nocional_ini_usdt) * 100.0, 2)
            if nocional_ini_usdt > 0.0
            else round(pnl_bruto_rem_pct * 100.0, 2)
        )

        vol_local = max(0.0005, float(pos.volatilidad_entry))
        lvr_usdt = round(0.5 * (vol_local ** 2) * nocional_ini_usdt * (hold_seg / 60.0), 4)

        ts_iso = datetime.fromtimestamp(t_now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        registro = RegistroOperacionCerrada(
            timestamp=ts_iso,
            symbol=pos.symbol,
            side=pos.side,
            z_score_entry=round(float(pos.z_score_entry), 4),
            ofi_entry=round(float(pos.ofi_entry), 4),
            hurst_entry=round(float(pos.hurst_entry), 4),
            pnl_percentage=pnl_pct_efectivo,
            pnl_usdt=pnl_neto_total_usdt,
            entry_price=round(float(pos.entry_price), 8),
            exit_price=round(float(exit_price), 8),
            qty=round(float(pos.qty_inicial), 6),
            motivo=str(motivo),
            hold_seg=round(hold_seg, 2),
            fees_usdt=fees_totales_usdt,
            map_usdt=round(nocional_ini_usdt, 4),
            lvr_usdt=lvr_usdt,
            cosecha_triz_50=bool(pos.cosecha_50_ejecutada),
        )

        self.operaciones.append(registro)
        if not cfg.es_modo_test():
            try:
                with open(self.ruta_jsonl, "a", encoding="utf-8") as f_out:
                    f_out.write(json.dumps(registro.to_dict(), ensure_ascii=False) + "\n")
            except Exception as exc:
                log_sniper(f"[CAJA NEGRA ERROR] Fallo persistiendo cierre: {exc}")

            registrar_evento_baul_ia(
                {
                    "tipo_evento": "TRADE_COMPLETO",
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "motivo": motivo,
                    "pnl_pct": pnl_pct_efectivo,
                    "pnl_usdt": pnl_neto_total_usdt,
                    "hold_seg": round(hold_seg, 2),
                    "mfe_pct": round(pos.max_pnl_pct_alcanzado * 100.0, 4),
                    "mae_pct": round(pos.min_pnl_pct_alcanzado * 100.0, 4),
                    "pnl_18s_pct": round(pos.pnl_18s_pct * 100.0, 4),
                    "pnl_45s_pct": round(pos.pnl_45s_pct * 100.0, 4),
                    "grado_senal": pos.grado_senal_entry,
                    "slot_modo": pos.slot_modo_apertura,
                    "iceberg_activo": pos.iceberg_activo,
                    "tag_percentil": pos.tag_percentil_entry,
                    "p_dia": pos.p_dia_entry,
                    "vector_entrada": {
                        "z": pos.z_score_entry,
                        "ofi": pos.ofi_entry,
                        "hurst": pos.hurst_entry,
                        "dp_pct": round(pos.delta_p_entry * 100.0, 4),
                        "ema900_pct": round(pos.ema900_dist_entry * 100.0, 4),
                        "lyap_pct": round(pos.lyapunov_entry * 100.0, 4),
                        "hawkes": pos.hawkes_entry,
                        "vpin": pos.vpin_entry,
                    },
                },
                ahora=t_now,
            )

        nuevo_bal = self.obtener_balance_contable_usdt()
        ESTADO_RAM.sincronizar_balance_uta(nuevo_bal, nuevo_bal)
        self.imprimir_hud_caja_negra()
        return registro

    def obtener_resumen_metricas(self) -> Dict[str, Any]:
        n_total = len(self.operaciones)
        wins = [op for op in self.operaciones if op.pnl_usdt > 0.0]
        losses = [op for op in self.operaciones if op.pnl_usdt <= 0.0]
        scratches = [op for op in self.operaciones if "SCRATCH" in op.motivo.upper()]

        n_wins = len(wins)
        n_losses = len(losses)
        n_scratches = len(scratches)
        n_efectivos = max(1, n_total - n_scratches)

        wr_clasico = (n_wins / n_total * 100.0) if n_total > 0 else 0.0
        wr_efectivo = (n_wins / n_efectivos * 100.0) if n_total > 0 else 0.0

        pnl_total = self.obtener_pnl_neto_total_usdt()
        mejor = max((op.pnl_usdt for op in self.operaciones), default=0.0)
        peor = min((op.pnl_usdt for op in self.operaciones), default=0.0)
        map_medio = (sum(op.map_usdt for op in self.operaciones) / n_total) if n_total > 0 else 0.0
        lvr_medio = (sum(op.lvr_usdt for op in self.operaciones) / n_total) if n_total > 0 else 0.0

        ahorro_scratch = 0.0
        for op in scratches:
            sl_teorico = op.map_usdt * (cfg.SL_INTERNO_PCT + cfg.FEE_TAKER_PCT)
            ahorro_scratch += max(0.0, sl_teorico - abs(op.pnl_usdt))

        # Velocidad geometrica g* de Kelly-Shannon
        g_star = 0.0
        if n_total > 0 and map_medio > 0.0:
            rets = [max(-0.95, op.pnl_usdt / max(1.0, cfg.CAPITAL_BASE_USDT)) for op in self.operaciones]
            g_star = sum(math.log(1.0 + r) for r in rets) / n_total

        balance_contable = self.obtener_balance_contable_usdt()
        progreso_meta_48h_pct = max(0.0, min(100.0, ((balance_contable - 10.0) / 4.0) * 100.0))

        return {
            "n_trades": n_total,
            "n_wins": n_wins,
            "n_losses": n_losses,
            "n_scratches": n_scratches,
            "cosechas_parciales": self.cosechas_parciales_count,
            "wr_clasico_pct": round(wr_clasico, 2),
            "wr_efectivo_pct": round(wr_efectivo, 2),
            "pnl_neto_usdt": round(pnl_total, 4),
            "mejor_trade_usdt": round(mejor, 4),
            "peor_trade_usdt": round(peor, 4),
            "map_medio_usdt": round(map_medio, 2),
            "lvr_medio_usdt": round(lvr_medio, 4),
            "ahorro_scratch_usdt": round(ahorro_scratch, 4),
            "g_star_geometric": round(g_star, 6),
            "balance_contable_usdt": balance_contable,
            "balance_real_uta_usdt": round(self.patrimonio_real_uta_usdt, 4),
            "progreso_meta_48h_pct": round(progreso_meta_48h_pct, 1),
        }

    def imprimir_hud_caja_negra(self) -> None:
        m = self.obtener_resumen_metricas()
        pnl_map_ratio = (m["pnl_neto_usdt"] / m["map_medio_usdt"]) if m["map_medio_usdt"] > 0 else 0.0
        log_sniper("╔══════ [CAJA NEGRA] OMEGA-PHANTOM V7.0 [APEX-CHRONOS 48H] ══════╗")
        log_sniper(
            f"║ Trades: {m['n_trades']:<3d} (W {m['n_wins']} / L {m['n_losses']} / S {m['n_scratches']}) "
            f"| WR Ef: {m['wr_efectivo_pct']:5.1f} % | Meta 14$: {m['progreso_meta_48h_pct']:4.1f}% ║"
        )
        log_sniper(
            f"║ PnL total: {m['pnl_neto_usdt']:+0.4f} USDT   mejor {m['mejor_trade_usdt']:+0.4f} / peor {m['peor_trade_usdt']:+0.4f}         ║"
        )
        log_sniper(
            f"║ MAP: {m['map_medio_usdt']:5.2f} USDT | PnL/MAP: {pnl_map_ratio:+0.4f} | LVR: {m['lvr_medio_usdt']:0.4f}               ║"
        )
        log_sniper(
            f"║ Balance: {m['balance_contable_usdt']:0.4f} USDT (base {cfg.CAPITAL_BASE_USDT:0.2f})   real: {m['balance_real_uta_usdt']:0.4f} USDT          ║"
        )
        log_sniper("╚════════════════════════════════════════════════════════════════╝")


CAJA_NEGRA: GestorCajaNegra = GestorCajaNegra()