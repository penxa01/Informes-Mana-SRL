// IndexedDB: guarda el catálogo (clientes y productos) para que la PWA
// funcione sin conexión. No guarda pedidos: eso es la cola offline
// (Tarea 10, cola.js), acá solo vive el catálogo de lectura.
const CatalogoDB = (() => {
  const DB_NAME = "mana-pedidos";
  const DB_VERSION = 1;
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
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return dbPromise;
  }

  async function reemplazarStore(nombre, filas) {
    const db = await abrir();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(nombre, "readwrite");
      const store = tx.objectStore(nombre);
      store.clear();
      for (const fila of filas) store.put(fila);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function listar(nombre) {
    const db = await abrir();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(nombre, "readonly");
      const req = tx.objectStore(nombre).getAll();
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function guardarMeta(clave, valor) {
    const db = await abrir();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("meta", "readwrite");
      tx.objectStore("meta").put({ clave, valor });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async function leerMeta(clave) {
    const db = await abrir();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("meta", "readonly");
      const req = tx.objectStore("meta").get(clave);
      req.onsuccess = () => resolve(req.result ? req.result.valor : undefined);
      req.onerror = () => reject(req.error);
    });
  }

  async function guardarCatalogo(version, clientes, productos) {
    await reemplazarStore("clientes", clientes);
    await reemplazarStore("productos", productos);
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
