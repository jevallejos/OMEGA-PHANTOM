#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #02: omega_phantom_v7_ram.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Nucleo de Memoria Compartida O(1), Contratos @dataclass, Logger Dual (CL/UTC),
Semaforo Ortogonal de 2 Slots (Zero-Risk Piggyback en BE+ y Delta-Neutral)
y Motor del Baul Cognitivo Forense IA (omega_phantom_v7_baul_ia.jsonl) con
Oraculo Contrafactual Diferido a +15.0s para SCAR-LOCK-01..13.
==============================================================================
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import omega_phantom_v7_config as cfg

_TZ_UTC = timezone.utc
_TZ_CHILE = timezone(timedelta(hours=-3))
_ARCHIVO_BAUL_IA: str = "omega_phantom_v7_baul_ia.jsonl"


@dataclass(slots=True)
class MetricaTick:
    """Fotografia microestructural instantanea O(1) de un activo a 50 Hz (20 ms)."""
    symbol: str
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    spread_pct: float = 0.0
    z_score: float = 0.0
    delta_p_pct: float = 0.0
    ema900: float = 0.0
    ema900_dist_pct: float = 0.0
    ema900_slope_pct: float = 0.0
    ofi_l1_l5: float = 0.0
    ofi_5s: float = 0.0
    ofi_ticks_confirmados_long: int = 0
    ofi_ticks_confirmados_short: int = 0
    hurst: float = 0.50
    lyapunov_acel_pct: float = 0.0
    hawkes_intensidad: float = 0.0
    vpin: float = 0.0
    volatilidad_local: float = 0.0
    ts_ultimo_pulso_toxico: float = 0.0
    ts_tick: float = field(default_factory=time.time)
    ofi_hibrido_50hz: float = 0.0
    flujo_taker_neto: float = 0.0
    precio_reserva_as: float = 0.0
    grado_senal: str = "ESTANDAR"


@dataclass(slots=True)
class PermisoRegimenActivo:
    """Vector de gobernanza asignado por el Enjambre Tri-Cortex en memoria RAM."""
    symbol: str
    modo_regimen: str = "LONG_ONLY"
    aprobado_groq: bool = True
    sizing_mult_gemini: float = 1.0
    caida_min_override_pct: float = 0.0
    cuarentena_hasta_ts: float = 0.0
    motivo: str = "INIT_DEFAULT"
    ts_actualizacion: float = field(default_factory=time.time)


@dataclass
class PosicionActiva:
    """
    Estado en memoria RAM de una posicion abierta en Bybit UTA.
    Soporta nativamente OMEGA-PHANTOM V7.0, Escalera 50/25/25, Semaforo
    Ortogonal de 2 Slots, Particion Iceberg y anatomia intratrade MFE/MAE.
    """
    symbol: str
    side: str
    qty_inicial: float
    qty_actual: float
    entry_price: float
    ts_apertura: float = field(default_factory=time.time)
    sl_interno_price: float = 0.0
    sl_bybit_price: float = 0.0
    z_score_entry: float = 0.0
    ofi_entry: float = 0.0
    hurst_entry: float = 0.45
    volatilidad_entry: float = 0.0020

    scratch_18s_evaluado: bool = False
    scratch_18s_activo: bool = False
    cosecha_50_ejecutada: bool = False
    ts_cosecha_50: float = 0.0
    cosecha_25_ejecutada: bool = False
    chain_jail_activo: bool = False
    eslabon_chain_jail: int = 0
    pre_escape_72s_enviado: bool = False
    pnl_realizado_parcial_usdt: float = 0.0
    fees_acumulados_usdt: float = 0.0
    max_pnl_pct_alcanzado: float = 0.0
    trinquete_be_armado: bool = False
    trinquete_ratchet_activo: bool = False
    trailing_activo: bool = False

    orden_salida_id: Optional[str] = None
    orden_salida_precio: float = 0.0
    orden_salida_qty: float = 0.0
    orden_salida_ts: float = 0.0
    orden_salida_tipo: str = ""

    cerrada: bool = False

    p_dia_entry: float = 0.25
    tag_percentil_entry: str = "P25_ELASTICO"
    ema900_dist_entry: float = 0.0
    ema900_slope_entry: float = 0.0
    delta_p_entry: float = 0.0
    lyapunov_entry: float = 0.0
    hawkes_entry: float = 0.0
    vpin_entry: float = 0.0
    z_btc_entry: float = 0.0
    ofi_btc_entry: float = 0.0
    kelly_fraccion_entry: float = 0.55
    hurst_max_elastico_entry: float = 0.475
    min_pnl_pct_alcanzado: float = 0.0
    pnl_18s_pct: float = 0.0
    pnl_45s_pct: float = 0.0
    snapshot_18s_tomado: bool = False
    snapshot_45s_tomado: bool = False
    modo_cosecha_ejecutado: str = "NONE"

    grado_senal_entry: str = "ESTANDAR"
    slot_modo_apertura: str = "SLOT_1_PRIMARIO"
    iceberg_activo: bool = False
    house_money_usdt_entry: float = 0.0
    margen_reservado_usdt: float = 0.0

    @property
    def entrada(self) -> float:
        return self.entry_price

    @entrada.setter
    def entrada(self, valor: float) -> None:
        self.entry_price = float(valor)

    @property
    def precio_entrada(self) -> float:
        return self.entry_price

    @precio_entrada.setter
    def precio_entrada(self, valor: float) -> None:
        self.entry_price = float(valor)

    @property
    def t_apertura(self) -> float:
        return self.ts_apertura

    @t_apertura.setter
    def t_apertura(self, valor: float) -> None:
        self.ts_apertura = float(valor)

    @property
    def timestamp_apertura(self) -> float:
        return self.ts_apertura

    @timestamp_apertura.setter
    def timestamp_apertura(self, valor: float) -> None:
        self.ts_apertura = float(valor)

    @property
    def qty(self) -> float:
        return self.qty_actual

    @qty.setter
    def qty(self, valor: float) -> None:
        self.qty_actual = float(valor)

    def edad_segundos(self, ahora: Optional[float] = None) -> float:
        t_now = ahora if ahora is not None else time.time()
        return max(0.0, t_now - self.ts_apertura)

    def calcular_pnl_bruto_pct(self, precio_actual: float) -> float:
        if self.entry_price <= 0.0 or precio_actual <= 0.0:
            return 0.0
        if self.side == "short":
            return (self.entry_price - precio_actual) / self.entry_price
        return (precio_actual - self.entry_price) / self.entry_price

    def actualizar_anatomia_intratrade(self, pnl_bruto_pct: float, edad_seg: float) -> None:
        if pnl_bruto_pct > self.max_pnl_pct_alcanzado:
            self.max_pnl_pct_alcanzado = pnl_bruto_pct
        if pnl_bruto_pct < self.min_pnl_pct_alcanzado:
            self.min_pnl_pct_alcanzado = pnl_bruto_pct
        if not self.snapshot_18s_tomado and edad_seg >= 18.0:
            self.pnl_18s_pct = round(pnl_bruto_pct, 6)
            self.snapshot_18s_tomado = True
        if not self.snapshot_45s_tomado and edad_seg >= 45.0:
            self.pnl_45s_pct = round(pnl_bruto_pct, 6)
            self.snapshot_45s_tomado = True


@dataclass(slots=True)
class RegistroOperacionCerrada:
    """Registro inmutable para persistencia en omega_phantom_v7_stats.jsonl."""
    timestamp: str
    symbol: str
    side: str
    z_score_entry: Optional[float]
    ofi_entry: Optional[float]
    hurst_entry: Optional[float]
    pnl_percentage: float
    pnl_usdt: float
    entry_price: float
    exit_price: float
    qty: float
    motivo: str
    hold_seg: float
    fees_usdt: float
    map_usdt: float
    lvr_usdt: float
    cosecha_triz_50: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_ARGV0_RAM: str = str(sys.argv[0]) if sys.argv else ""
_ES_DAEMON_O_SUITE: bool = any(
    _k in _ARGV0_RAM
    for _k in ("omega_phantom_v7_main", "omega_phantom_v7_test", "omega_phantom_v7_oos")
)


def formatear_sello_tiempo(ts: Optional[float] = None) -> str:
    t_val = ts if ts is not None else time.time()
    dt_utc = datetime.fromtimestamp(t_val, tz=_TZ_UTC)
    dt_cl = dt_utc.astimezone(_TZ_CHILE)
    ms = int((t_val - int(t_val)) * 1000.0)
    return f"[{dt_cl.strftime('%Y-%m-%d %H:%M:%S')}.{ms:03d} CL | {dt_utc.strftime('%H:%M:%S')} UTC]"


def registrar_evento_baul_ia(evento: Dict[str, Any], ahora: Optional[float] = None) -> bool:
    if cfg.es_modo_test() or not isinstance(evento, dict):
        return False

    t_val = float(ahora) if ahora is not None else time.time()
    dt_utc = datetime.fromtimestamp(t_val, tz=_TZ_UTC)
    registro: Dict[str, Any] = {
        "ts_utc": dt_utc.isoformat(timespec="seconds"),
        "sello_dual": formatear_sello_tiempo(t_val),
    }
    registro.update(evento)

    try:
        ruta_baul = cfg.ROOT_DIR / _ARCHIVO_BAUL_IA
        with open(ruta_baul, "a", encoding="utf-8") as f_baul:
            f_baul.write(json.dumps(registro, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def log_sniper(mensaje: str, escribir_disco: bool = True) -> Optional[str]:
    if not _ES_DAEMON_O_SUITE and "Whitelist O(1) inicializada" in str(mensaje):
        return None

    sello = formatear_sello_tiempo()
    linea = f"{sello} {mensaje}"
    sys.stdout.write(linea + "\n")
    sys.stdout.flush()

    if escribir_disco:
        try:
            if cfg.es_modo_test():
                ruta_test = cfg.ROOT_DIR / ".test_omega_phantom_v7.log"
                with open(ruta_test, "a", encoding="utf-8") as f_test:
                    f_test.write(linea + "\n")
            else:
                ruta_sesion = cfg.ROOT_DIR / cfg.ARCHIVO_LOG_SESION
                ruta_hist = cfg.ROOT_DIR / cfg.ARCHIVO_LOG_HISTORICO
                with open(ruta_sesion, "a", encoding="utf-8") as f_ses:
                    f_ses.write(linea + "\n")
                with open(ruta_hist, "a", encoding="utf-8") as f_hist:
                    f_hist.write(linea + "\n")
        except Exception:
            pass

    return linea


log_sniper.info = log_sniper
log_sniper.warning = log_sniper
log_sniper.error = log_sniper
log_sniper.debug = log_sniper


class EstadoGlobalRAM:
    """Almacen centralizado en memoria RAM con complejidad O(1) y Semaforo Ortogonal."""

    def __init__(self) -> None:
        self.patrimonio_total_usdt: float = cfg.CAPITAL_BASE_USDT
        self.margen_libre_usdt: float = cfg.CAPITAL_BASE_USDT
        self.margen_bloqueado_usdt: float = 0.0
        self.high_water_mark_usdt: float = cfg.CAPITAL_BASE_USDT

        self.slot_ocupado: bool = False
        self.orden_en_vuelo_symbol: Optional[str] = None
        self.posiciones_activas: Dict[str, PosicionActiva] = {}

        self.pausa_macro_hasta_ts: float = 0.0
        self.eventos_caida_recientes: Dict[str, float] = {}
        self.ultimo_sl_short_precio: Dict[str, Tuple[float, float]] = {}

        todos_simbolos = tuple(cfg.PARES_CAMPEONES_ALFA) + (cfg.SIMBOLO_CENTINELA_MACRO,)
        self.ticks_ram: Dict[str, MetricaTick] = {
            sym: MetricaTick(symbol=sym) for sym in todos_simbolos
        }
        self.permisos_ram: Dict[str, PermisoRegimenActivo] = {
            sym: PermisoRegimenActivo(symbol=sym) for sym in cfg.PARES_CAMPEONES_ALFA
        }

        self.pares_excluidos_lote: set[str] = set()
        self.cola_eventos: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=1024)

        self.auditorias_escudo_pendientes: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.ultimo_ts_auditoria_escudo: Dict[Tuple[str, str], float] = {}
        self.ultimo_modo_slot_autorizado: str = "SLOT_1_PRIMARIO"

    def verificar_slot_ortogonal_disponible(
        self,
        symbol: str,
        side_solicitado: str = "long",
        z_score_actual: float = 0.0,
    ) -> Tuple[bool, str]:
        """
        Evalua en O(1) si el Semaforo Ortogonal de 2 Slots (OMEGA-PHANTOM V7.0)
        autoriza el disparo cuando existe 1 posicion abierta en custodia:
          1. Condicion Free-Ride (Riesgo $0.00): La Posicion 1 ya ejecuto su
             cosecha parcial, armo su trinquete Break-Even o escalo en Chain-Jail.
          2. Condicion Delta-Neutral: La Posicion 1 opera en direccion opuesta y
             la nueva senal tiene conviccion extrema (|Z| >= 4.00).
        """
        if not self.slot_ocupado and not self.posiciones_activas and self.orden_en_vuelo_symbol is None:
            return True, "SLOT_1_PRIMARIO"

        if cfg.es_modo_test():
            return False, "SLOT_OCUPADO"

        if self.orden_en_vuelo_symbol is not None:
            return False, "ORDEN_EN_VUELO_ACTIVA"

        n_activas = len(self.posiciones_activas)
        if n_activas == 0:
            return False, "SLOT_OCUPADO"
        if n_activas >= 2 or symbol in self.posiciones_activas:
            return False, "MAX_2_SLOTS_ORTOGONALES_OCUPADOS"
        if self.margen_libre_usdt < cfg.MARGEN_MINIMO_OPERACION_USDT:
            return False, "MARGEN_LIBRE_INSUFICIENTE_SLOT2"

        pos_actual = next(iter(self.posiciones_activas.values()))
        if pos_actual.cerrada:
            return True, "SLOT_1_CERRANDO"

        if (
            pos_actual.cosecha_50_ejecutada
            or pos_actual.trinquete_be_armado
            or pos_actual.eslabon_chain_jail >= 1
        ):
            return True, "SLOT_2_FREE_RIDE_BE_LOCKED"

        side_norm = str(side_solicitado).lower()
        if str(pos_actual.side).lower() != side_norm and abs(float(z_score_actual)) >= 4.00:
            return True, "SLOT_2_DELTA_NEUTRAL_HEDGE"

        return False, "SLOT_OCUPADO"

    def consultar_permiso_o1(
        self,
        symbol: str,
        side_solicitado: str = "long",
        z_score_actual: float = 0.0,
        ahora: Optional[float] = None,
    ) -> Tuple[bool, str, float]:
        t_now = ahora if ahora is not None else time.time()
        side_norm = str(side_solicitado).lower()
        es_test = cfg.es_modo_test()

        if t_now < self.pausa_macro_hasta_ts:
            if es_test or side_norm != "short":
                return False, "PAUSA_CONTAGIO_MACRO", 0.0

        if self.slot_ocupado or self.orden_en_vuelo_symbol is not None:
            ok_ortogonal, modo_slot = self.verificar_slot_ortogonal_disponible(
                symbol=symbol,
                side_solicitado=side_norm,
                z_score_actual=z_score_actual,
            )
            if not ok_ortogonal:
                return False, "SLOT_OCUPADO", 0.0
            self.ultimo_modo_slot_autorizado = modo_slot
        else:
            self.ultimo_modo_slot_autorizado = "SLOT_1_PRIMARIO"

        if symbol in cfg.PARES_VETADOS_OOS or symbol in self.pares_excluidos_lote:
            return False, "PAR_VETADO_O_LOTE_INDIVISIBLE", 0.0

        perm = self.permisos_ram.get(symbol)
        if perm is None:
            return False, "SIMBOLO_NO_REGISTRADO", 0.0

        if t_now < perm.cuarentena_hasta_ts:
            restante = int(perm.cuarentena_hasta_ts - t_now)
            return False, f"CUARENTENA_ACTIVA_{restante}S", 0.0

        if not perm.aprobado_groq or perm.modo_regimen == "VETO_TOXIC":
            return False, f"VETO_TRICORTEX_{perm.modo_regimen}", 0.0

        if side_norm == "long":
            if perm.modo_regimen == "SHORT_ONLY":
                return False, "REGIMEN_SHORT_ONLY_ACTIVO", 0.0
            if perm.modo_regimen == "EXTREME_Z_ONLY" and z_score_actual > -4.50:
                return False, "EXIGE_EXTREME_Z_4.5", 0.0
        elif side_norm == "short":
            if not cfg.MODO_BIDIRECCIONAL:
                return False, "MODO_SHORT_DESACTIVADO", 0.0
            if perm.modo_regimen == "LONG_ONLY" and z_score_actual < 3.50:
                return False, "REGIMEN_LONG_ONLY_ACTIVO", 0.0

        return True, "APROBADO_O1", perm.sizing_mult_gemini

    def encolar_auditoria_escudo_15s(
        self,
        symbol: str,
        side: str,
        scar_id: str,
        precio_bloqueo: float,
        tag_percentil: str = "P50_ELASTICO",
        p_dia: float = 0.50,
        detalle: str = "",
        ahora: Optional[float] = None,
    ) -> None:
        if cfg.es_modo_test() or precio_bloqueo <= 0.0:
            return

        t_now = float(ahora) if ahora is not None else time.time()
        clave = (symbol, str(scar_id))
        if (t_now - self.ultimo_ts_auditoria_escudo.get(clave, 0.0)) < 15.0:
            return

        self.ultimo_ts_auditoria_escudo[clave] = t_now
        tk = self.ticks_ram.get(symbol)
        tk_btc = self.ticks_ram.get(cfg.SIMBOLO_CENTINELA_MACRO)

        self.auditorias_escudo_pendientes[clave] = {
            "symbol": symbol,
            "side": str(side).lower(),
            "scar_id": str(scar_id),
            "precio_bloqueo": float(precio_bloqueo),
            "ts_bloqueo": t_now,
            "tag_percentil": str(tag_percentil),
            "p_dia": round(float(p_dia), 4),
            "detalle": str(detalle),
            "z_score": round(float(tk.z_score), 3) if tk else 0.0,
            "dp_pct": round(float(tk.delta_p_pct) * 100.0, 3) if tk else 0.0,
            "ema900_pct": round(float(tk.ema900_dist_pct) * 100.0, 3) if tk else 0.0,
            "ema_slope_pct": round(float(tk.ema900_slope_pct) * 100.0, 4) if tk else 0.0,
            "ofi_l1_l5": round(float(tk.ofi_l1_l5), 3) if tk else 0.0,
            "hurst": round(float(tk.hurst), 4) if tk else 0.45,
            "lyap_acel_pct": round(float(tk.lyapunov_acel_pct) * 100.0, 4) if tk else 0.0,
            "hawkes": round(float(tk.hawkes_intensidad), 3) if tk else 0.0,
            "vpin": round(float(tk.vpin), 3) if tk else 0.0,
            "z_btc": round(float(tk_btc.z_score), 3) if tk_btc else 0.0,
            "ofi_btc": round(float(tk_btc.ofi_l1_l5), 3) if tk_btc else 0.0,
        }

    def evaluar_auditorias_escudo_vencidas(
        self,
        symbol: str,
        precio_actual: float,
        ahora: Optional[float] = None,
    ) -> int:
        if (
            cfg.es_modo_test()
            or not self.auditorias_escudo_pendientes
            or precio_actual <= 0.0
        ):
            return 0

        t_now = float(ahora) if ahora is not None else time.time()
        procesadas = 0

        for clave in list(self.auditorias_escudo_pendientes.keys()):
            if clave[0] != symbol:
                continue
            item = self.auditorias_escudo_pendientes.get(clave)
            if item is None:
                continue
            dt_seg = t_now - float(item["ts_bloqueo"])
            if dt_seg < 15.0:
                continue

            self.auditorias_escudo_pendientes.pop(clave, None)
            p_bloq = float(item["precio_bloqueo"])
            side = str(item["side"])
            ret_15s = (
                ((precio_actual - p_bloq) / p_bloq)
                if side == "long"
                else ((p_bloq - precio_actual) / p_bloq)
            )
            nocional_ref = 25.0 if symbol in cfg.CLASE_TIER1_LIQUIDO else cfg.NOCIONAL_MAX_HIGH_BETA_USDT

            if ret_15s <= -0.0015:
                veredicto = "CAPITAL_SALVADO_TRUE_SHIELD"
                impacto_usdt = round(abs(ret_15s) * nocional_ref, 4)
            elif ret_15s >= 0.0024:
                veredicto = "OPORTUNIDAD_PERDIDA_FALSE_REJECTION"
                impacto_usdt = -round(max(0.0, ret_15s - 0.0004) * nocional_ref, 4)
            else:
                veredicto = "RUIDO_NEUTRO_LATERAL"
                impacto_usdt = 0.0

            evento_baul = {
                "tipo_evento": "AUDITORIA_ESCUDO_15S",
                "veredicto_ia": veredicto,
                "scar_id": item["scar_id"],
                "symbol": symbol,
                "side": side,
                "tag_percentil": item["tag_percentil"],
                "p_dia": item["p_dia"],
                "precio_bloqueo": p_bloq,
                "precio_15s_despues": round(float(precio_actual), 8),
                "excursion_15s_pct": round(ret_15s * 100.0, 4),
                "impacto_estimado_usdt": impacto_usdt,
                "dt_evaluacion_seg": round(dt_seg, 2),
                "detalle_filtro": item["detalle"],
                "vector_x": {
                    "z": item["z_score"],
                    "dp_pct": item["dp_pct"],
                    "ema900_pct": item["ema900_pct"],
                    "ema_slope_pct": item["ema_slope_pct"],
                    "ofi": item["ofi_l1_l5"],
                    "hurst": item["hurst"],
                    "lyap_pct": item["lyap_acel_pct"],
                    "hawkes": item["hawkes"],
                    "vpin": item["vpin"],
                    "z_btc": item["z_btc"],
                    "ofi_btc": item["ofi_btc"],
                },
            }
            registrar_evento_baul_ia(evento_baul, ahora=t_now)
            procesadas += 1

        return procesadas

    def aplicar_cuarentena(self, symbol: str, duracion_seg: float, motivo: str) -> None:
        perm = self.permisos_ram.get(symbol)
        if perm is None:
            perm = PermisoRegimenActivo(symbol=symbol)
            self.permisos_ram[symbol] = perm
        nuevo_fin = time.time() + max(0.0, float(duracion_seg))
        if nuevo_fin > perm.cuarentena_hasta_ts:
            perm.cuarentena_hasta_ts = nuevo_fin
            perm.motivo = motivo

    def reservar_margen_atomico(
        self,
        symbol: str,
        margen_usdt: float,
        side_solicitado: str = "long",
        z_score_actual: float = 0.0,
    ) -> bool:
        if self.slot_ocupado or self.orden_en_vuelo_symbol is not None:
            tk = self.ticks_ram.get(symbol)
            z_eval = z_score_actual if z_score_actual != 0.0 else (float(tk.z_score) if tk else 0.0)
            ok_ortogonal, modo_slot = self.verificar_slot_ortogonal_disponible(
                symbol=symbol,
                side_solicitado=side_solicitado,
                z_score_actual=z_eval,
            )
            if not ok_ortogonal:
                return False
            self.ultimo_modo_slot_autorizado = modo_slot
        else:
            self.ultimo_modo_slot_autorizado = "SLOT_1_PRIMARIO"

        margen_req = float(margen_usdt)
        if margen_req < cfg.MARGEN_MINIMO_OPERACION_USDT or margen_req > self.margen_libre_usdt:
            return False

        self.slot_ocupado = True
        self.orden_en_vuelo_symbol = symbol
        self.margen_libre_usdt = max(0.0, self.margen_libre_usdt - margen_req)
        self.margen_bloqueado_usdt += margen_req
        return True

    def liberar_margen_atomico(self, symbol: str, margen_usdt: float = 0.0) -> None:
        if self.orden_en_vuelo_symbol == symbol:
            self.orden_en_vuelo_symbol = None
        pos_removida = self.posiciones_activas.pop(symbol, None)
        margen_lib = float(margen_usdt)
        if margen_lib <= 0.0 and pos_removida is not None and pos_removida.margen_reservado_usdt > 0.0:
            margen_lib = float(pos_removida.margen_reservado_usdt)

        if not self.posiciones_activas and self.orden_en_vuelo_symbol is None:
            self.slot_ocupado = False
            self.margen_bloqueado_usdt = 0.0
            self.margen_libre_usdt = self.patrimonio_total_usdt
        else:
            self.slot_ocupado = True
            if margen_lib > 0.0:
                self.margen_bloqueado_usdt = max(0.0, self.margen_bloqueado_usdt - margen_lib)
                self.margen_libre_usdt = max(0.0, self.patrimonio_total_usdt - self.margen_bloqueado_usdt)

    def sincronizar_balance_uta(self, total_usdt: float, libre_usdt: float) -> None:
        if total_usdt > 0.0:
            self.patrimonio_total_usdt = float(total_usdt)
            if total_usdt > self.high_water_mark_usdt:
                self.high_water_mark_usdt = float(total_usdt)
        if not self.slot_ocupado and not self.posiciones_activas:
            self.margen_libre_usdt = float(libre_usdt if libre_usdt > 0.0 else total_usdt)
            self.margen_bloqueado_usdt = max(0.0, self.patrimonio_total_usdt - self.margen_libre_usdt)

    def calcular_drawdown_actual_pct(self) -> float:
        if self.high_water_mark_usdt <= 0.0:
            return 0.0
        dd = (self.high_water_mark_usdt - self.patrimonio_total_usdt) / self.high_water_mark_usdt
        return max(0.0, dd)


ESTADO_RAM: EstadoGlobalRAM = EstadoGlobalRAM()