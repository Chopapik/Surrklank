import type { FirmwareSnapshot } from '../firmware/firmware.types';
import type { ConnectionSnapshot } from './connection.types';

export interface DeviceStateMessage {
  type: 'state';
  connection: ConnectionSnapshot;
  firmware: FirmwareSnapshot;
}
