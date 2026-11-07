import { useDeviceControls } from './features/application/useDeviceControls';

const controlStyle =
  '[font:inherit] p-[8px] [margin:6px_8px_6px_0] text-black bg-white ' +
  '[border:2px_outset_#fff] rounded-none disabled:text-[#666] disabled:bg-[#ddd]';
const sectionStyle = 'py-[18px] [border-top:1px_solid_#fff] mt-[20px]';
const preStyle = 'whitespace-pre-wrap [overflow-wrap:anywhere]';

export function App() {
  const { sendAction, atx, connectionState, firmwareState, busy, busyReason, pingText } = useDeviceControls();
  const { connection, ready, connected, statusLabel, socketLabel } = connectionState;
  const { firmware, ports, selectedPort, setSelectedPort, requestUpload, error } = firmwareState;

  return (
    <>
      <h1>Surrklank</h1>
      <small className="block min-h-[1.2em]">{socketLabel}</small>

      <section className={sectionStyle}>
        <h2 className="text-[20px] min-h-[1.2em]">{statusLabel}</h2>
        <button className={controlStyle} disabled={!ready || busy} onClick={() => sendAction('connect')}>
          Połącz
        </button>
        <button className={controlStyle} disabled={!ready || busy} onClick={() => sendAction('disconnect')}>
          Rozłącz
        </button>
        <button className={controlStyle} disabled={!ready || busy || !connected} onClick={() => sendAction('ping')}>
          Ping
        </button>
        <p>{pingText}</p>
        <p className="text-white">{error || firmware.error || connection?.error || ''}</p>
        <small>Ostatni odczyt firmware</small>
        <pre className={preStyle}>{connection?.device ? JSON.stringify(connection.device, null, 2) : ''}</pre>
      </section>

      <section className={sectionStyle}>
        <h2 className="text-[20px]">Zasilanie ATX</h2>
        <button className={controlStyle} role="switch" aria-label="Zasilanie ATX"
          aria-checked={atx.on === true} aria-describedby={busyReason ? 'device-busy-reason' : undefined}
          disabled={atx.on === null || busy || atx.pending}
          onClick={() => atx.setState(atx.on ? 'off' : 'on')}>
          {atx.on === null ? 'Stan nieznany' : atx.on ? 'ATX włączony' : 'ATX wyłączony'}
        </button>
        {busyReason && <p id="device-busy-reason" role="status">{busyReason}</p>}
        <small>Stan wyjścia ESP32 sterującego tranzystorem, bez pomiaru napięcia.</small>
        {atx.error && <p role="alert">{atx.error}</p>}
      </section>

      <section className={sectionStyle}>
        <h2 className="text-[20px] min-h-[1.2em]">Firmware</h2>
        <select className={controlStyle} value={selectedPort} onChange={(event) => setSelectedPort(event.target.value)}>
          {ports.map((port) => <option key={port.port} value={port.port}>{port.port}</option>)}
        </select>
        <button className={controlStyle} disabled={!ready || busy} onClick={() => requestUpload('usb')}>
          Kompiluj i wgraj przez USB
        </button>
        <button className={controlStyle} disabled={!ready || busy} onClick={() => requestUpload('ota')}>
          Kompiluj i wgraj przez BLE OTA
        </button>
        <p>{firmware.stage}</p>
        <progress className="w-full accent-white" max="100" value={firmware.progress ?? 0} />
        <pre className={preStyle}>{firmware.result ? JSON.stringify(firmware.result, null, 2) : ''}</pre>
      </section>
    </>
  );
}
