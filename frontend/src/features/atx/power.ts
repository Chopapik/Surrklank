// Actuator module k reports ULT of slots M1-M4 on bits 4(k-1)..4(k-1)+3. A
// module that does not answer reads LOW on every slot, like four faults.
export function describeActuators(faults: number | null, modules = 2): string[] {
  return Array.from({ length: modules }, (_, index) => {
    const label = `Moduł aktuatorów ${index + 1}: `;
    if (faults === null) return label + 'nieznany (magistrala wyłączona)';
    const bits = (faults >> (index * 4)) & 0x0f;
    if (bits === 0x0f) return label + 'brak odpowiedzi';
    if (bits === 0) return label + 'odpowiada, bez błędów';
    const slots = [0, 1, 2, 3].filter((slot) => bits & (1 << slot)).map((slot) => `M${slot + 1}`);
    return label + `błąd ULT: ${slots.join(', ')}`;
  });
}
