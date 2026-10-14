/** Read-only helper for an AUTHENTICATED official Tuya IDE extension worker.
 * Pass the official ark object; this file has no standalone HTTP client,
 * credentials, startup side effects, device publishing or configuration writes.
 * See diagnostics/rgbic-scenes/library-recovery.md before use.
 */
const PID = 'example-product-led';
const DEVICE = 'example-led-0000000001';
const API = 'tuya.m.light.panel.library.data.get';
const text = value => typeof value === 'string' && value.length <= 256 ? value : undefined;
const integer = value => Number.isSafeInteger(value) && value >= 0 ? value : undefined;

export async function recoverSceneLibrary(ark) {
  let started = false;
  try {
    const project = await ark.project.getInfo();
    if (!project?.id) throw new Error('context');
    const mode = await ark.storage.get(`debugMode_${project.id}`);
    const deviceId = await ark.storage.get(`current_debug_device_id_${project.id}`);
    const productId = await ark.storage.get(`current_debug_product_id_${project.id}`);
    if (mode !== 'real' || deviceId !== DEVICE || productId !== PID) {
      return {status: 'context_mismatch', requests: 0, writes_sent: 0};
    }
    // Never export/log the customer session or attempt to supply Cloud credentials.
    if (!await ark.auth.getCustomerUserInfo()) {
      return {status: 'official_login_required', requests: 0, writes_sent: 0};
    }
    started = true;
    const response = await ark.http.atop({api: API, version: '1.0', params: {
      bizId: deviceId, bizType: 0, libType: 'SCENE_LIB', libVersion: '', libDataType: 4,
    }});
    const body = response?.data;
    if (body?.success !== true) {
      const code = String(body?.errorCode ?? body?.code ?? '');
      return {status: 'api_denied_or_unavailable', requests: 1, writes_sent: 0,
        error_code: /^\d{1,12}$/.test(code) ? code : null};
    }
    if (!Array.isArray(body.result) || body.result.length > 1000) throw new Error('shape');
    let count = 0;
    const result = body.result.map(plate => {
      if (!Array.isArray(plate.data)) throw new Error('shape');
      return {plateName: text(plate.plateName), plateId: integer(plate.plateId),
        data: plate.data.map(group => {
          if (!Array.isArray(group.items)) throw new Error('shape');
          return {items: group.items.map(item => {
            if (++count > 10000) throw new Error('limit');
            return {sceneName: text(item.sceneName), sceneNameRosettaKey: text(item.sceneNameRosettaKey),
              sceneId: integer(item.sceneId), dpCode: text(item.dpCode), dpId: integer(item.dpId),
              sceneData: text(item.sceneData), plateId: integer(item.plateId)};
          })};
        })};
    });
    return {format: 'smart-tray-tuya-library-v1', status: 'read_ok', source_api: API,
      source_version: '1.0', product_id: PID, device_id_masked: 'exampl…0001',
      binding_evidence: 'official_ide_context_matches_cached_cloud_metadata',
      fetched_at: new Date().toISOString(), result, requests: 1, writes_sent: 0};
  } catch {
    // Intentionally omit raw exceptions, sessions, headers and response bodies.
    return {status: 'official_context_or_response_error', requests: started ? 1 : 0, writes_sent: 0};
  }
}
