/**
 * 全局状态与常量。
 */
export const API = `${window.location.origin}/api/v1`;
export const CACHE_NS = 'wy-dw:v1:';

export const state = {
  currentPage: 'raw',
  currentTable: '网优项目_gps定位北京明细数据_20251201_20251207',
  tables: [],
  fields: [],
  decisions: [],
  selectedField: null,
};
