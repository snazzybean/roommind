/** Temperature unit symbol (°C or °F). */
export function tempUnit(useImperial: boolean): string {
  return useImperial ? "\u00B0F" : "\u00B0C";
}
