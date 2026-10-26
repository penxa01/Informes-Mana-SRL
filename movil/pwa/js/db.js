// IndexedDB local de la PWA. Una sola base ("mana-pedidos") con estos usos:
//  - CatalogoDB: clientes y productos de lectura, para trabajar sin conexión.
//  - ColaDB: pedidos cargados en el teléfono, a la espera de enviarse (ver cola.js).
//  - ColaRepartoDB: entregas y ubicaciones del reparto por enviar (ver cola-reparto.js).
//  - MetaDB: valores sueltos (por ejemplo, la última lista de entregas que vio el reparto).
const BaseLocal = (() => {
  const DB_NAME = "mana-pedidos";
  const DB_VERSION = 3; // 2: store "cola"; 3: store "cola_reparto" (lo anterior se conserva)
  let dbPromise = null;

  function abrir() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains("clientes")) db.createObjectStore("clientes", { keyPath: "id" });
        if (!db.objectStoreNames.contains("productos")) db.createObjectStore("productos", { keyPath: "id" });
        if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta", { keyPath: "clave" });
        if (!db.objectStoreNames.contains("cola")) db.createObjectStore("cola", { keyPath: "uuid" });
        if (!db.objectStoreNames.contains("cola_reparto")) db.createObjectStore("cola_reparto", { keyPath: "uuid" });
      };
      req.onsuccess = () => {
        const db = req.result;
        // Si otra pestaña/instancia pide una versión nueva, no la bloqueamos.
        db.onversionchange = () => db.close();
        resolve(db);
      };
      req.onerror = () => reject(req.error);
    });
    return dbPromise;
  }

  // Corre `accion(store)` dentro de una transacción y resuelve cuando ésta
  // termina; si `accion` devuelve un request, resuelve con su resultado.
  async function operar(nombre, modo, accion) {
    const db = await abrir();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(nombre, modo);
      const req = accion(tx.objectStore(nombre));
      tx.oncomplete = () => resolve(req ? req.result : undefined);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  }

  return { operar };
})();

const CatalogoDB = (() => {
  const listar = (nombre) => BaseLocal.operar(nombre, "readonly", (s) => s.getAll());

  const guardarMeta = (clave, valor) => BaseLocal.operar("meta", "readwrite", (s) => void s.put({ clave, valor }));

  async function leerMeta(clave) {
    const fila = await BaseLocal.operar("meta", "readonly", (s) => s.get(clave));
    return fila ? fila.valor : undefined;
  }

  const reemplazar = (nombre, filas) =>
    BaseLocal.operar(nombre, "readwrite", (s) => {
      s.clear();
      for (const fila of filas) s.put(fila);
    });

  async function guardarCatalogo(version, clientes, productos) {
    await reemplazar("clientes", clientes);
    await reemplazar("productos", productos);
    await guardarMeta("version", version);
    await guardarMeta("sincronizado_en", new Date().toISOString());
  }

  return {
    guardarCatalogo,
    clientes: () => listar("clientes"),
    productos: () => listar("productos"),
    version: () => leerMeta("version"),
    sincronizadoEn: () => leerMeta("sincronizado_en"),
  };
})();

const ColaDB = (() => ({
  todos: () => BaseLocal.operar("cola", "readonly", (s) => s.getAll()),
  agregar: (pedido) => BaseLocal.operar("cola", "readwrite", (s) => void s.put(pedido)),
  borrar: (uuid) => BaseLocal.operar("cola", "readwrite", (s) => void s.delete(uuid)),

  // Lee y escribe en la MISMA transacción: así dos actualizaciones seguidas
  // no se pisan entre sí.
  actualizar: (uuid, cambios) =>
    BaseLocal.operar("cola", "readwrite", (s) => {
      const lectura = s.get(uuid);
      lectura.onsuccess = () => {
        if (lectura.result) s.put({ ...lectura.result, ...cambios });
      };
    }),
}))();

const MetaDB = (() => ({
  guardar: (clave, valor) => BaseLocal.operar("meta", "readwrite", (s) => void s.put({ clave, valor })),
  leer: async (clave) => {
    const fila = await BaseLocal.operar("meta", "readonly", (s) => s.get(clave));
    return fila ? fila.valor : undefined;
  },
  borrar: (clave) => BaseLocal.operar("meta", "readwrite", (s) => void s.delete(clave)),
}))();

const ColaRepartoDB = (() => ({
  todos: () => BaseLocal.operar("cola_reparto", "readonly", (s) => s.getAll()),
  agregar: (accion) => BaseLocal.operar("cola_reparto", "readwrite", (s) => void s.put(accion)),
  borrar: (uuid) => BaseLocal.operar("cola_reparto", "readwrite", (s) => void s.delete(uuid)),
  actualizar: (uuid, cambios) =>
    BaseLocal.operar("cola_reparto", "readwrite", (s) => {
      const lectura = s.get(uuid);
      lectura.onsuccess = () => {
        if (lectura.result) s.put({ ...lectura.result, ...cambios });
      };
    }),
}))();
