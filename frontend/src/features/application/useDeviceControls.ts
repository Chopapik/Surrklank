import { useAtx } from '../atx/useAtx';
import { useConnection } from '../connection/useConnection';
import { useDeviceSocket } from '../connection/useDeviceSocket';
import { useFirmware } from '../firmware/useFirmware';

// Coordinates controls whose availability depends on several features.
export function useDeviceControls() {
  const sendAction = useDeviceSocket();
  const atx = useAtx();
  const connectionState = useConnection();
  const firmwareState = useFirmware();
  const operation = connectionState.connection?.operation;
  const maintenance = firmwareState.firmware.busy || firmwareState.uploadPending || operation === 'firmware_update';
  const busy = maintenance || !!operation;
  let busyReason: string | null = null;
  if (maintenance) {
    busyReason = 'Trwa aktualizacja firmware. Sterowanie ATX i inne operacje są teraz niedostępne.';
  } else if (operation) {
    busyReason = 'ESP32 wykonuje inną operację. Poczekaj na jej zakończenie.';
  }

  const ping = connectionState.connection?.last_ping;
  let pingText = 'Ping uruchamia się tylko po kliknięciu.';
  if (ping) {
    pingText = ping.ok ? `Ostatni ping: ${ping.reply} · ${ping.rtt_ms} ms` : ping.error ?? '';
  }

  return { sendAction, atx, connectionState, firmwareState, busy, busyReason, pingText };
}
