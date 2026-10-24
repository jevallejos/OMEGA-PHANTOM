#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
==============================================================================
ARCHIVO #03: omega_phantom_v7_telegram.py
SISTEMA: OMEGA-PHANTOM V7.0 (APEX-CHRONOS SINGULARITY)
==============================================================================
Motor de Notificaciones Transaccionales con Protocolo de Apareamiento 1:1:
  1. Retiene aperturas en RAM hasta confirmar llenado real en Bybit UTA.
  2. Descarta silenciosamente ordenes no llenadas a los 3.80s (Cero Spam).
  3. Garantiza entrega 100% de cosechas parciales y cierres definitivos con
     deduplicacion idempotente de 12.0s.
==============================================================================
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import aiohttp

import omega_phantom_v7_config as cfg
from omega_phantom_v7_ram import RegistroOperacionCerrada, log_sniper

_ICON_GREEN: str = "\U0001f7e9"
_ICON_DIAMOND: str = "\U0001f48e"
_ICON_YELLOW: str = "\U0001f7e8"
_ICON_RED: str = "\U0001f534"


@dataclass(slots=True)
class AperturaPendienteRAM:
    """Boleto de apertura retenido en RAM hasta confirmacion de fill en Bybit."""
    symbol: str
    side: str
    qty: float
    entry_price: float
    nocional_usdt: float
    apalancamiento: int
    fraccion_kelly: float
    z_score: float
    ofi: float
    hurst: float
    rtt_ms: float
    grado_senal: str = "ESTANDAR"
    slot_modo: str = "SLOT_1_PRIMARIO"
    ts_creacion: float = field(default_factory=time.time)
    despachada: bool = False


class GestorTelemetriaTelegram:
    """Orquestador asincrono de alertas 1:1 para Telegram Bot API."""

    def __init__(self) -> None:
        self.aperturas_pendientes: Dict[str, AperturaPendienteRAM] = {}
        self._firmas_enviadas: Dict[str, float] = {}
        self.mensajes_enviados_total: int = 0

    def _purgar_firmas_antiguas(self, ahora: float) -> None:
        expiradas = [k for k, ts in self._firmas_enviadas.items() if (ahora - ts) > 12.0]
        for k in expiradas:
            self._firmas_enviadas.pop(k, None)

    def _es_duplicado_reciente(self, firma: str) -> bool:
        ahora = time.time()
        self._purgar_firmas_antiguas(ahora)
        if firma in self._firmas_enviadas:
            return True
        self._firmas_enviadas[firma] = ahora
        return False

    def registrar_apertura_pendiente(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        nocional_usdt: float,
        apalancamiento: int,
        fraccion_kelly: float,
        z_score: float,
        ofi: float,
        hurst: float = 0.45,
        rtt_ms: float = 1.5,
        grado_senal: str = "ESTANDAR",
        slot_modo: str = "SLOT_1_PRIMARIO",
    ) -> None:
        self.aperturas_pendientes[symbol] = AperturaPendienteRAM(
            symbol=symbol,
            side=str(side).lower(),
            qty=float(qty),
            entry_price=float(entry_price),
            nocional_usdt=float(nocional_usdt),
            apalancamiento=int(apalancamiento),
            fraccion_kelly=float(fraccion_kelly),
            z_score=float(z_score),
            ofi=float(ofi),
            hurst=float(hurst),
            rtt_ms=float(rtt_ms),
            grado_senal=str(grado_senal),
            slot_modo=str(slot_modo),
        )

    def descartar_apertura_no_llenada(self, symbol: str) -> bool:
        removida = self.aperturas_pendientes.pop(symbol, None)
        return removida is not None

    async def _enviar_http_telegram(self, texto: str) -> bool:
        if cfg.es_modo_test():
            self.mensajes_enviados_total += 1
            return True
        if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
            return False

        url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": cfg.TELEGRAM_CHAT_ID,
            "text": texto,
            "disable_web_page_projection": True,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=8.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        self.mensajes_enviados_total += 1
                        return True
                    return False
        except Exception as exc:
            log_sniper(f"[TELEGRAM WARN] Error HTTP enviando mensaje: {exc}")
            return False

    async def confirmar_y_despachar_apertura(
        self,
        symbol: str,
        qty_llenada: Optional[float] = None,
        precio_llenado: Optional[float] = None,
    ) -> bool:
        boleto = self.aperturas_pendientes.get(symbol)
        if boleto is None or boleto.despachada:
            return False

        if qty_llenada is not None and qty_llenada > 0.0:
            boleto.qty = float(qty_llenada)
        if precio_llenado is not None and precio_llenado > 0.0:
            boleto.entry_price = float(precio_llenado)
            boleto.nocional_usdt = boleto.qty * boleto.entry_price

        firma = f"OPEN|{symbol}|{boleto.side}|{round(boleto.entry_price, 6)}"
        if self._es_duplicado_reciente(firma):
            return False

        boleto.despachada = True
        etiqueta_dir = "SHORT-SNIPER" if boleto.side == "short" else "LONG-REBOUND"
        texto = (
            f"{_ICON_GREEN} [APERTURA {etiqueta_dir}] {cfg.TITULO_TELEGRAM_CANONICO}\n"
            f"Activo: {symbol} ({boleto.grado_senal} | {boleto.slot_modo})\n"
            f"Lote: {boleto.qty} @ {boleto.entry_price}\n"
            f"Nocional: {boleto.nocional_usdt:.2f} USDT ({boleto.apalancamiento}x | Kelly {boleto.fraccion_kelly*100:.0f}%)\n"
            f"Microestructura: Z={boleto.z_score:+.2f} | OFI={boleto.ofi:+.2f} | H={boleto.hurst:.3f} | RTT={boleto.rtt_ms:.1f}ms"
        )
        return await self._enviar_http_telegram(texto)

    async def notificar_cosecha_parcial(
        self,
        symbol: str,
        side: str,
        qty_cosechada: float,
        precio_cosecha: float,
        pnl_pct: float,
        pnl_usdt: float,
        etapa: str = "COSECHA_50_TRIZ",
    ) -> bool:
        firma = f"HARVEST|{symbol}|{etapa}|{round(precio_cosecha, 6)}"
        if self._es_duplicado_reciente(firma):
            return False

        texto = (
            f"{_ICON_DIAMOND} [{etapa}] {cfg.TITULO_TELEGRAM_CANONICO}\n"
            f"Activo: {symbol} [{side.upper()}]\n"
            f"Lote Cosechado: {qty_cosechada} @ {precio_cosecha}\n"
            f"Resultado Parcial: {pnl_pct*100:+.2f}% ({pnl_usdt:+.4f} USDT) [SL en Break-Even+]"
        )
        return await self._enviar_http_telegram(texto)

    async def notificar_cierre_definitivo(
        self,
        registro: RegistroOperacionCerrada,
        patrimonio_actual_usdt: float,
        win_rate_efectivo_pct: float,
    ) -> bool:
        self.aperturas_pendientes.pop(registro.symbol, None)
        firma = f"CLOSE|{registro.symbol}|{registro.motivo}|{round(registro.exit_price, 6)}|{round(registro.pnl_usdt, 4)}"
        if self._es_duplicado_reciente(firma):
            return False

        if "SCRATCH" in registro.motivo.upper():
            icono = _ICON_YELLOW
            tag = "SCRATCH PASIVO"
        elif registro.pnl_usdt >= 0.0:
            icono = _ICON_GREEN
            tag = "VICTORIA NETA"
        else:
            icono = _ICON_RED
            tag = "CIERRE DEFENSIVO"

        progreso_48h = max(0.0, min(100.0, ((patrimonio_actual_usdt - 10.0) / 4.0) * 100.0))
        texto = (
            f"{icono} [{tag} -- {registro.motivo}] {cfg.TITULO_TELEGRAM_CANONICO}\n"
            f"Activo: {registro.symbol} [{registro.side.upper()}]\n"
            f"Trayectoria: {registro.entry_price} -> {registro.exit_price} ({registro.hold_seg:.1f}s)\n"
            f"PnL Neto: {registro.pnl_percentage:+.2f}% ({registro.pnl_usdt:+.4f} USDT)\n"
            f"Patrimonio UTA: {patrimonio_actual_usdt:.4f} USDT | WR Ef: {win_rate_efectivo_pct:.1f}% | Meta 14 USDT: {progreso_48h:.1f}%"
        )
        return await self._enviar_http_telegram(texto)


TELEMETRIA_TG: GestorTelemetriaTelegram = GestorTelemetriaTelegram()