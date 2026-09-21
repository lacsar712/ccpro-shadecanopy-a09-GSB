<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const list = ref([])
const summary = ref([])
const greenhouses = ref([])
const zones = ref([])
const error = ref('')
const filterGreenhouse = ref('')
const filterShipped = ref('')
const activeId = ref(null)

function localInputValue(d = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const palletForm = reactive({
  greenhouseId: '',
  palletNo: '',
  packedAt: localInputValue(),
})

const lineForm = reactive({
  zoneId: '',
  kg: 1,
  grade: '甲',
})

const activePallet = computed(() => list.value.find((p) => p.id === activeId.value) || null)
const activeZones = computed(() =>
  activePallet.value
    ? zones.value.filter((z) => z.greenhouseId === activePallet.value.greenhouseId)
    : []
)

function fmtTime(v) {
  return v ? new Date(v).toLocaleString() : '—'
}

async function loadRefs() {
  const [{ data: g }, { data: z }] = await Promise.all([
    api.get('/greenhouses/'),
    api.get('/zones/'),
  ])
  greenhouses.value = g.results || g
  zones.value = z.results || z
  if (!palletForm.greenhouseId && greenhouses.value.length) {
    palletForm.greenhouseId = greenhouses.value[0].id
  }
}

async function load() {
  error.value = ''
  try {
    const params = {}
    if (filterGreenhouse.value) params.greenhouseId = filterGreenhouse.value
    if (filterShipped.value) params.shipped = filterShipped.value
    const { data } = await api.get('/pallets/', { params })
    list.value = data.results || data
  } catch {
    error.value = '加载托盘列表失败'
  }
}

async function loadSummary() {
  const { data } = await api.get('/pallets/summary/')
  summary.value = data
}

async function refreshAll() {
  await Promise.all([load(), loadSummary()])
}

function errText(e, fallback) {
  const d = e.response?.data
  if (!d) return fallback
  if (typeof d === 'string') return d
  if (d.detail) return d.detail
  return Object.entries(d)
    .map(([k, v]) => `${k}: ${[].concat(v).join('；')}`)
    .join('；')
}

async function createPallet() {
  error.value = ''
  try {
    await api.post('/pallets/', {
      greenhouseId: Number(palletForm.greenhouseId),
      palletNo: palletForm.palletNo.trim(),
      packedAt: new Date(palletForm.packedAt).toISOString(),
    })
    palletForm.palletNo = ''
    palletForm.packedAt = localInputValue()
    await refreshAll()
  } catch (e) {
    error.value = errText(e, '新建托盘失败')
  }
}

async function ship(row) {
  error.value = ''
  try {
    await api.post(`/pallets/${row.id}/ship/`)
    await refreshAll()
  } catch (e) {
    error.value = errText(e, '发运失败')
  }
}

async function removePallet(row) {
  if (!confirm(`确认删除托盘 ${row.palletNo} 及其全部装盘行？`)) return
  error.value = ''
  try {
    await api.delete(`/pallets/${row.id}/`)
    if (activeId.value === row.id) activeId.value = null
    await refreshAll()
  } catch (e) {
    error.value = errText(e, '删除托盘失败')
  }
}

function toggleActive(row) {
  activeId.value = activeId.value === row.id ? null : row.id
  if (activePallet.value && activeZones.value.length) {
    lineForm.zoneId = activeZones.value[0].id
  }
}

async function addLine() {
  error.value = ''
  try {
    await api.post('/pallet-lines/', {
      palletId: activePallet.value.id,
      zoneId: Number(lineForm.zoneId),
      kg: String(lineForm.kg),
      grade: lineForm.grade,
    })
    await refreshAll()
  } catch (e) {
    error.value = errText(e, '装入失败')
  }
}

async function removeLine(line) {
  if (!confirm('确认移除该装盘行？')) return
  error.value = ''
  try {
    await api.delete(`/pallet-lines/${line.id}/`)
    await refreshAll()
  } catch (e) {
    error.value = errText(e, '移除装盘行失败')
  }
}

onMounted(async () => {
  await loadRefs()
  await refreshAll()
})
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>发运托盘</h1>
        <p>鲜品托盘挂温室，装入多分区称重行，满足条件后可发运</p>
      </div>
      <div class="actions">
        <select v-model="filterGreenhouse" @change="load">
          <option value="">全部温室</option>
          <option v-for="g in greenhouses" :key="g.id" :value="g.id">{{ g.name }}</option>
        </select>
        <select v-model="filterShipped" @change="load">
          <option value="">全部状态</option>
          <option value="false">未发运</option>
          <option value="true">已发运</option>
        </select>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">按温室汇总</h3>
      <table>
        <thead>
          <tr>
            <th>温室</th>
            <th>托盘数</th>
            <th>已发运</th>
            <th>公斤合计</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in summary" :key="row.greenhouseId">
            <td>{{ row.greenhouseName }}</td>
            <td>{{ row.palletCount }}</td>
            <td>{{ row.shippedCount }}</td>
            <td>{{ row.totalKg }} kg</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">新建托盘</h3>
      <div class="form-grid">
        <label>
          所属温室
          <select v-model="palletForm.greenhouseId">
            <option v-for="g in greenhouses" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
        </label>
        <label>托盘号<input v-model="palletForm.palletNo" placeholder="如 TP-003" /></label>
        <label>装盘时刻<input v-model="palletForm.packedAt" type="datetime-local" /></label>
      </div>
      <div class="actions" style="margin-top:12px">
        <button class="btn" :disabled="!palletForm.palletNo.trim()" @click="createPallet">保存</button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>温室</th>
            <th>托盘号</th>
            <th>装盘时刻</th>
            <th>状态</th>
            <th>行数</th>
            <th>公斤合计</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in list" :key="row.id">
            <td>{{ row.greenhouseName }}</td>
            <td>{{ row.palletNo }}</td>
            <td>{{ fmtTime(row.packedAt) }}</td>
            <td>
              <span v-if="row.shippedAt" class="badge done">已发运 {{ fmtTime(row.shippedAt) }}</span>
              <span v-else class="badge running">未发运</span>
            </td>
            <td>{{ row.lineCount }}</td>
            <td>{{ row.totalKg }} kg</td>
            <td class="actions">
              <button class="btn ghost" @click="toggleActive(row)">
                {{ activeId === row.id ? '收起' : '装盘行' }}
              </button>
              <button v-if="!row.shippedAt" class="btn secondary" @click="ship(row)">发运</button>
              <button v-if="!row.shippedAt" class="btn danger" @click="removePallet(row)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="activePallet" class="panel">
      <h3 style="margin-top:0">
        装盘行 · {{ activePallet.greenhouseName }} / {{ activePallet.palletNo }}
        <span v-if="activePallet.shippedAt" class="badge done">已发运，禁止再装入</span>
      </h3>
      <table>
        <thead>
          <tr>
            <th>分区</th>
            <th>公斤数</th>
            <th>等级</th>
            <th v-if="!activePallet.shippedAt">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="line in activePallet.lines" :key="line.id">
            <td>{{ line.zoneCode }}</td>
            <td>{{ line.kg }} kg</td>
            <td><span class="badge growing">{{ line.grade }}</span></td>
            <td v-if="!activePallet.shippedAt" class="actions">
              <button class="btn danger" @click="removeLine(line)">移除</button>
            </td>
          </tr>
          <tr v-if="!activePallet.lines.length">
            <td :colspan="activePallet.shippedAt ? 3 : 4" style="color: var(--muted)">暂无装盘行</td>
          </tr>
        </tbody>
      </table>

      <template v-if="!activePallet.shippedAt">
        <div class="form-grid" style="margin-top:14px">
          <label>
            分区（限本温室）
            <select v-model="lineForm.zoneId">
              <option v-for="z in activeZones" :key="z.id" :value="z.id">{{ z.zoneCode }}</option>
            </select>
          </label>
          <label>公斤数<input v-model.number="lineForm.kg" type="number" step="0.001" min="0.001" /></label>
          <label>
            等级
            <select v-model="lineForm.grade">
              <option value="甲">甲</option>
              <option value="乙">乙</option>
            </select>
          </label>
        </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn" :disabled="!lineForm.zoneId" @click="addLine">装入</button>
        </div>
      </template>
    </div>
  </div>
</template>
