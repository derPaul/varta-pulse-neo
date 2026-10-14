# VARTA pulse neo – Home Assistant Integration

Custom Integration für [Home Assistant](https://www.home-assistant.io/), die einen
**VARTA pulse neo** (z. B. pulse neo 6) lokal per **Modbus TCP** ausliest – ohne Cloud,
ohne zusätzliche Python-Abhängigkeiten.

Die Registerbelegung ist bei VARTA element, pulse, pulse neo, link und flex gleich,
daher sollte die Integration auch mit diesen Geräten funktionieren.

## Sensoren

| Sensor | Einheit | Hinweis |
|---|---|---|
| Ladezustand | % | |
| Batterieleistung | W | positiv = Laden, negativ = Entladen |
| Ladeleistung / Entladeleistung | W | jeweils nur positive Werte |
| Netzleistung | W | positiv = Bezug, negativ = Einspeisung |
| Netzbezug / Netzeinspeisung | W | jeweils nur positive Werte |
| Status | – | Startet, Bereit, Lädt, Entlädt, Standby, Fehler, Passiv, Inselbetrieb |
| Gesamt geladene Energie | kWh | Zähler des Geräts |
| Batterie geladen / entladen | kWh | in HA aus der Leistung integriert |
| Netzbezug / Netzeinspeisung Energie | kWh | in HA aus der Leistung integriert |
| Scheinleistung | VA | standardmäßig deaktiviert |
| PV-Sensor-Leistung | W | nur mit optionalem VARTA PV-Sensor, standardmäßig deaktiviert |
| Installierte Kapazität, Anzahl Batteriemodule, Fehlercode | | Diagnose |

Seriennummer und Firmware-Versionen erscheinen in den Geräteinformationen.

### Energie-Dashboard

Der Speicher selbst liefert nur einen Zähler für die *geladene* Energie. Für das
Energie-Dashboard berechnet die Integration deshalb vier Energiezähler
(Batterie geladen/entladen, Netzbezug/-einspeisung) aus den abgefragten
Leistungswerten (Trapezregel, Zählerstand bleibt über Neustarts erhalten).
Unter *Einstellungen → Dashboards → Energie* einfach eintragen:

- **Netz:** „Netzbezug Energie“ und „Netzeinspeisung Energie“
- **Batteriespeicher:** „Batterie geladen“ und „Batterie entladen“

Falls ein separater Stromzähler (z. B. vom Netzbetreiber) vorhanden ist, ist dessen
Zähler genauer als die integrierten Werte.

## Voraussetzungen

- Der pulse neo ist per LAN im selben Netz wie Home Assistant.
- **Modbus TCP ist aktiviert** (über das Webinterface des Speichers bzw. durch den
  Installateur/VARTA-Service). Port 502.
- Am besten bekommt der Speicher im Router eine feste IP-Adresse.

## Installation

### HACS (empfohlen)

1. HACS → ⋮ → *Benutzerdefinierte Repositories* →
   `https://github.com/derpaul/varta-pulse-neo`, Kategorie *Integration*.
2. „VARTA pulse neo“ installieren und Home Assistant neu starten.

### Manuell

Den Ordner `custom_components/varta_pulse_neo` nach
`<config>/custom_components/varta_pulse_neo` kopieren und Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → „VARTA pulse neo“*

| Feld | Standard |
|---|---|
| Host | IP-Adresse des Speichers |
| Port | 502 |
| Unit-ID | 255 |

Das Abfrageintervall (Standard 10 s) lässt sich danach über *Konfigurieren* ändern.
Host/Port lassen sich über *Neu konfigurieren* anpassen.

## Hinweise

- Die Integration liest nur – sie schreibt keine Register und verändert nichts am
  Speicher.
- Viele VARTA-Geräte erlauben nur wenige gleichzeitige Modbus-Verbindungen. Wenn
  parallel z. B. evcc oder ioBroker abfragen, kann es zu Verbindungsfehlern kommen.
- Registerquelle: VARTA Modbus-Tabelle (wie u. a. von
  [evcc](https://github.com/evcc-io/evcc) und `vartastorage` verwendet).

## Icon

Das Integrations-Icon liegt in `custom_components/varta_pulse_neo/brand/` und wird
ab Home Assistant 2026.3 automatisch angezeigt. Es ist ein eigenes Motiv und kein
offizielles VARTA-Logo.

## Entwicklung

```bash
pip install -r requirements_test.txt
pytest
ruff check custom_components tests
```
