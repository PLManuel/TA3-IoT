"""
pip install -r requirements.txt

python simulador_dht22.py
python simulador_dht22.py --broker 192.168.1.50 --intervalo 10 --acelerar 24
"""

import argparse
import json
import math
import random
import sys
import time
import uuid
from datetime import datetime, timedelta

import paho.mqtt.client as mqtt

class SensorDHT22Simulado:

    def __init__(self, sensor_id, ubicacion, temp_media, hum_media, amplitud_temp):
        self.sensor_id = sensor_id
        self.ubicacion = ubicacion
        self.temp_media = temp_media
        self.hum_media = hum_media
        self.amplitud_temp = amplitud_temp
        self._desvio_temp = 0.0
        self._desvio_hum = 0.0

    def leer(self, hora_del_dia):
        ciclo = math.sin((hora_del_dia - 9) / 24 * 2 * math.pi)

        self._desvio_temp = 0.9 * self._desvio_temp + random.gauss(0, 0.08)
        self._desvio_hum = 0.9 * self._desvio_hum + random.gauss(0, 0.3)

        temperatura = self.temp_media + self.amplitud_temp * ciclo + self._desvio_temp
        humedad = (self.hum_media
                   - 2.5 * self.amplitud_temp * ciclo
                   - 1.5 * self._desvio_temp
                   + self._desvio_hum)

        temperatura = min(max(temperatura, -40.0), 80.0)
        humedad = min(max(humedad, 0.0), 100.0)
        return round(temperatura, 1), round(humedad, 1)


def hora_simulada(inicio_real, inicio_mono, factor):
    transcurrido = (time.monotonic() - inicio_mono) * factor
    t = inicio_real + timedelta(seconds=transcurrido)
    return t.hour + t.minute / 60 + t.second / 3600


def al_conectar(client, userdata, flags, reason_code, properties):
    if reason_code.is_failure:
        print(f"[MQTT] Conexión rechazada por el broker: {reason_code}")
    else:
        print(f"[MQTT] Conectado a {userdata['broker']}:{userdata['puerto']}")


def al_desconectar(client, userdata, flags, reason_code, properties):
    if not userdata["saliendo"]:
        print(f"[MQTT] Conexión perdida ({reason_code}). Reintentando...")


def main():
    parser = argparse.ArgumentParser(description="Nodo IoT simulado DHT22 -> MQTT")
    parser.add_argument("--broker", default="localhost", help="host del broker (por defecto localhost)")
    parser.add_argument("--puerto", type=int, default=1883, help="puerto MQTT (por defecto 1883)")
    parser.add_argument("--intervalo", type=float, default=10.0,
                        help="segundos entre lecturas (la TA3 pide 10)")
    parser.add_argument("--acelerar", type=float, default=1.0,
                        help="acelera el ciclo diario; 24 = un día completo en una hora")
    args = parser.parse_args()

    sensores = [
        SensorDHT22Simulado("dht22-sim-01", "sala", temp_media=23.5, hum_media=60.0, amplitud_temp=2.5),
        SensorDHT22Simulado("dht22-sim-02", "laboratorio", temp_media=21.0, hum_media=50.0, amplitud_temp=1.2),
    ]

    estado = {"broker": args.broker, "puerto": args.puerto, "saliendo": False}
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"ta3-nodo-sim-{uuid.uuid4().hex[:6]}",
        userdata=estado,
    )
    client.on_connect = al_conectar
    client.on_disconnect = al_desconectar
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        client.connect(args.broker, args.puerto, keepalive=60)
    except OSError as error:
        print(f"No se pudo conectar a {args.broker}:{args.puerto} ({error}).")
        sys.exit(1)

    client.loop_start()
    print(f"Publicando en 'iot/raspberrypi/temperatura' cada {args.intervalo:g} s.\n")

    inicio_real = datetime.now()
    inicio_mono = time.monotonic()
    siguiente = time.monotonic()
    try:
        while True:
            hora = hora_simulada(inicio_real, inicio_mono, args.acelerar)
            ts = datetime.now().astimezone().isoformat(timespec="seconds")
            for sensor in sensores:
                temperatura, humedad = sensor.leer(hora)
                payload = {
                    "sensor": sensor.sensor_id,
                    "ubicacion": sensor.ubicacion,
                    "temperatura": temperatura,
                    "humedad": humedad,
                    "ts": ts,
                }
                info = client.publish('iot/raspberrypi/temperatura', json.dumps(payload), qos=1)
                marca = "OK" if info.rc == mqtt.MQTT_ERR_SUCCESS else "SIN CONEXIÓN"
                print(f"{ts}  {sensor.ubicacion:<12} {temperatura:5.1f} °C  {humedad:5.1f} %  [{marca}]")
            siguiente += args.intervalo
            time.sleep(max(0.0, siguiente - time.monotonic()))
    except KeyboardInterrupt:
        print("\nDeteniendo el nodo...")
    finally:
        estado["saliendo"] = True
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
