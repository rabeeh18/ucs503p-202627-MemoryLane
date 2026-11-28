// The search model in the browser: bge-small-en-v1.5 (full precision, the
// server's model) run by transformers.js on WebAssembly. Its vectors match the
// server's to about 1e-7.
//
// The code is bundled with the extension (vendor/); the weights (~130 MB) are
// downloaded once from the MemoryLane site and kept in the browser's cache.
import { SETTINGS } from "./settings.js";

const BATCH = 8;

/**
 * @param {object} transformers  the transformers.js module
 * @param {{modelHost: string, wasmPath?: string, model?: string}} where
 */
export async function createEmbedder(transformers, { modelHost, wasmPath, model = "bge-small-en-v1.5" }) {
    const { pipeline, env } = transformers;
    env.allowLocalModels = false;
    env.allowRemoteModels = true;
    env.remoteHost = modelHost;
    env.remotePathTemplate = "{model}/";
    if (wasmPath) {
        env.backends.onnx.wasm.wasmPaths = wasmPath;
        env.backends.onnx.wasm.numThreads = 1; // no SharedArrayBuffer in extension pages
        env.backends.onnx.wasm.proxy = false;
    }
    const extractor = await pipeline("feature-extraction", model, { dtype: "fp32", device: "wasm" });

    async function embed(texts) {
        const out = [];
        for (let i = 0; i < texts.length; i += BATCH) {
            const result = await extractor(texts.slice(i, i + BATCH), { pooling: "cls", normalize: true });
            out.push(...result.tolist());
        }
        return out;
    }

    return {
        embedPassages: embed,
        embedQuery: async (query) => (await embed([`${SETTINGS.EMBEDDING_QUERY_PREFIX}${query}`]))[0],
        dispose: () => extractor.dispose && extractor.dispose(),
    };
}
