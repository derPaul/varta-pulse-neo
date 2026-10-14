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
| Vollzyklen | – | gesamt geladene Energie ÷ installierte Kapazität |
| Wirkungsgrad | % | entladene ÷ geladene Energie, korrigiert um die Änderung des Ladezustands; erst ab 1 kWh geladener Energie |
| Problem | an/aus | an bei Fehlercode ≠ 0 oder Status „Fehler“ (Attribut `error_code`) |
| Batterie geladen / entladen | kWh | in HA aus der Leistung integriert |
| Netzbezug / Netzeinspeisung Energie | kWh | in HA aus der Leistung integriert |
| Scheinleistung | VA | standardmäßig deaktiviert |
| PV-Sensor-Leistung | W | nur mit optionalem VARTA PV-Sensor, standardmäßig deaktiviert |
| Installierte Kapazität, Anzahl Batteriemodule, Fehlercode | | Diagnose |

Seriennummer und Firmware-Versionen erscheinen in den Geräteinformationen.

### Zusätzlich mit Webinterface-Zugang (optional)

Wird bei der Einrichtung das Passwort des Webinterfaces angegeben (Benutzer
`user1`, siehe unten), liest die Integration zusätzlich `/cgi/data` aus:

| Sensor | Hinweis |
|---|---|
| Batterie geladen / entladen (Gerätezähler) | echte Zähler des Speichers (DC), kWh |
| Speicher AC-Aufnahme / AC-Abgabe | Energie, die der Speicher aus dem Hausnetz aufnimmt / abgibt |
| Netzbezug / Netzeinspeisung (Gerätezähler) | Zähler des Netzsensors – bitte einmal mit dem Stromzähler vergleichen |
| Wirkungsgrad Batterie (DC) / gesamt (AC) | aus den Gerätezählern |
| Batteriegesundheit, nutzbare Kapazität, Ladezyklen | |
| Batterie-, Wechselrichter-, Umgebungstemperatur | |
| Batteriespannung, Zellspannungsdifferenz (min./max. Zellspannung) | Diagnose |
| Netzspannung, Netzfrequenz, Netzstrom L1–L3, Blindleistung | |
| Max. Lade-/Entladeleistung, Lüfter, Betriebsstunden, Systemstarts | Diagnose, teils deaktiviert |
| Notstrombetrieb | an/aus |

Für das Energie-Dashboard sind die Gerätezähler genauer als die aus der Leistung
berechneten Zähler.

### Energie-Dashboard

Der Speicher selbst liefert nur einen Zähler für die *geladene* Energie. Für das
Energie-Dashboard berechnet die Integration deshalb vier Energiezähler
(Batterie geladen/entladen, Netzbezug/-einspeisung) aus den abgefragten
Leistungswerten (Trapezregel). Die Zählerstände werden in Home Assistant gespeichert
und bleiben über Neustarts erhalten.
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

| Benutzername (Webinterface) | `user1` (optional) |
| Passwort (Webinterface) | leer = nur Modbus |
| Webinterface über HTTPS | aus |

Das Abfrageintervall (Standard 10 s) lässt sich danach über *Konfigurieren* ändern.
Host/Port lassen sich über *Neu konfigurieren* anpassen.

### Zugangsdaten für das Webinterface

Laut Betriebsanleitung meldet man sich als Endkunde mit dem Benutzer `user1` an. Das
Erstpasswort sind die ersten 6 Zeichen von „Code #1“ auf dem Cryptocode-Aufkleber am
Gehäuse. Über „Passwort vergessen?“ lässt es sich mit dem vollständigen Code #1 (PUK)
zurücksetzen.

Lehnt der Speicher die Zugangsdaten ab, versucht die Integration es **nicht**
wiederholt (sonst sperrt der Speicher den Zugang), sondern fordert in Home Assistant
zur erneuten Eingabe auf.

## Hinweise

- Die Integration liest nur – sie schreibt keine Register und ändert keine
  Einstellungen am Speicher.
- Ohne HTTPS wird das Passwort des Webinterfaces unverschlüsselt im Heimnetz
  übertragen. Den Speicher am besten nicht aus dem Internet erreichbar machen.
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
