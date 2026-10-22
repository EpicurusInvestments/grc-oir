import "@testing-library/jest-dom/vitest";

import { configure } from "@testing-library/dom";

// Fix (reportado por el usuario: una corrida de CI falló en una prueba que localmente
// pasaba siempre) — el timeout default de `waitFor`/`findBy*` (1000ms) alcanza de sobra
// en una máquina de desarrollo, pero un runner de CI con menos CPU, corriendo los ~16
// archivos de `ordenes` en paralelo, puede tardar más en resolver un efecto async
// genuino (no es que la prueba esté mal escrita, es que la aserción SÍ se cumple, solo
// que un poco después del segundo 1). Se sube a 5s para todo el repo, sin tocar ninguna
// prueba — más barato y más robusto que afinar timeouts prueba por prueba.
configure({ asyncUtilTimeout: 5000 });
