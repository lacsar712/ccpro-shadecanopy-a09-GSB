<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import api from '../api'

const list = ref([])
const summary = ref([])
const greenhouses = ref([])
const zones = ref([])
const error = ref('')
const lineError = ref('')
const filterGreenhouseId = ref('')
const filterShipped = ref('')

const selected = ref(null)
const lines = ref([])

function localInputValue(d = new Date()) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const form = reactive({
  greenhouseId: '',
  palletNo: '',
  packedAt: localInputValue(),
})

const lineForm = reactive({
  zoneId: '',
  kg: 1,
  grade: '甲',
})

const selectedZones = computed(() => {
  if (!selected.value) return []
  return zones.value.filter((z) => z.greenhouseId === selected.value.greenhouseId)
})

const linesTotalKg = computed(() =>
  lines.value.reduce((acc, l) => acc + Number(l.kg), 0).toFixed(3)
)

async function loadGreenhouses() {
  const { data } = await api.get('/greenhouses/')
  greenhouses.value = data.results || data
  if (!form.greenhouseId && greenhouses.value.length) {
    form.greenhouseId = greenhouses.value[0].id
  }
}

async function loadZones() {
  const { data } = await api.get('/zones/')
  zones.value = data.results || data
}

async function load() {
  error.value = ''
  try {
    const params = {}
    if (filterGreenhouseId.value) params.greenhouseId = filterGreenhouseId.value
    if (filterShipped.value) params.shipped = filterShipped.value
    const { data } = await api.get('/pallets/', { params })
    list.value = data.results || data
  } catch {
    error.value = '加载托盘失败'
  }
}

async function loadSummary() {
  const { data } = await api.get('/pallets/summary/')
  summary.value = data
}

async function loadLines() {
  if (!selected.value) return
  const { data } = await api.get('/pallet-lines/', {
    params: { palletId: selected.value.id },
  })
  lines.value = data.results || data
}

async function createPallet() {
  error.value = ''
  try {
    await api.post('/pallets/', {
      greenhouseId: Number(form.greenhouseId),
      palletNo: form.palletNo,
      packedAt: new Date(form.packedAt).toISOString(),
    })
    form.palletNo = ''
    form.packedAt = localInputValue()
    await Promise.all([load(), loadSummary()])
  } catch (e) {
    error.value = JSON.stringify(e.response?.data || '保存失败')
  }
}

async function removePallet(row) {
  if (!confirm(`确认删除托盘 ${row.palletNo} 及其全部装盘行？`)) return
  await api.delete(`/pallets/${row.id}/`)
  if (selected.value?.id === row.id) {
    selected.value = null
    lines.value = []
  }
  await Promise.all([load(), loadSummary()])
}

function pick(row) {
  selected.value = row
  lineError.value = ''
  lineForm.zoneId = ''
  lineForm.kg = 1
  lineForm.grade = '甲'
  loadLines()
}

async function addLine() {
  lineError.value = ''
  try {
    await api.post('/pallet-lines/', {
      palletId: selected.value.id,
      zoneId: Number(lineForm.zoneId),
      kg: lineForm.kg,
      grade: lineForm.grade,
    })
    lineForm.kg = 1
    await Promise.all([loadLines(), load(), loadSummary()])
  } catch (e) {
    lineError.value = JSON.stringify(e.response?.data || '装入失败')
  }
}

async function removeLine(id) {
  await api.delete(`/pallet-lines/${id}/`)
  await Promise.all([loadLines(), load(), loadSummary()])
}

async function ship(row) {
  error.value = ''
  try {
    await api.post(`/pallets/${row.id}/ship/`)
    if (selected.value?.id === row.id) {
      selected.value = { ...selected.value, shippedAt: new Date().toISOString() }
    }
    await Promise.all([load(), loadSummary()])
  } catch (e) {
    error.value = e.response?.data?.detail || JSON.stringify(e.response?.data || '发运失败')
  }
}

onMounted(async () => {
  await loadGreenhouses()
  await loadZones()
  await Promise.all([load(), loadSummary()])
})
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>发运托盘</h1>
        <p>托盘挂温室、装入各分区称重行；≥2 行且公斤合计 &gt; 5 方可发运</p>
      </div>
      <div class="actions">
        <select v-model="filterGreenhouseId" @change="load">
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
      <h3 style="margin-top:0">新建托盘</h3>
      <div class="form-grid">
        <label>
          所属温室
          <select v-model="form.greenhouseId">
            <option v-for="g in greenhouses" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
        </label>
        <label>托盘号<input v-model="form.palletNo" required placeholder="同温室内唯一" /></label>
        <label>装盘时刻<input v-model="form.packedAt" type="datetime-local" /></label>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="actions" style="margin-top:12px">
        <button class="btn" @click="createPallet">保存</button>
      </div>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>温室</th>
            <th>托盘号</th>
            <th>装盘时刻</th>
            <th>发运时刻</th>
            <th>行数</th>
            <th>公斤合计</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in list" :key="row.id">
            <td>{{ row.greenhouseName }}</td>
            <td>{{ row.palletNo }}</td>
            <td>{{ new Date(row.packedAt).toLocaleString() }}</td>
            <td>{{ row.shippedAt ? new Date(row.shippedAt).toLocaleString() : '—' }}</td>
            <td>{{ row.lineCount }}</td>
            <td>{{ Number(row.totalKg).toFixed(3) }}</td>
            <td>
              <span class="badge" :class="row.shippedAt ? 'done' : 'scheduled'">
                {{ row.shippedAt ? '已发运' : '未发运' }}
              </span>
            </td>
            <td class="actions">
              <button class="btn ghost" @click="pick(row)">装行</button>
              <button v-if="!row.shippedAt" class="btn secondary" @click="ship(row)">发运</button>
              <button class="btn danger" @click="removePallet(row)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="selected" class="panel">
      <h3 style="margin-top:0">
        装盘行 — {{ selected.greenhouseName }} / {{ selected.palletNo }}
        <span class="badge" :class="selected.shippedAt ? 'done' : 'scheduled'">
          {{ selected.shippedAt ? '已发运' : '未发运' }}
        </span>
      </h3>
      <template v-if="!selected.shippedAt">
        <div class="form-grid">
          <label>
            分区（{{ selected.greenhouseName }}）
            <select v-model="lineForm.zoneId">
              <option v-for="z in selectedZones" :key="z.id" :value="z.id">{{ z.zoneCode }}</option>
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
        <p v-if="lineError" class="error">{{ lineError }}</p>
        <div class="actions" style="margin-top:12px">
          <button class="btn" :disabled="!lineForm.zoneId" @click="addLine">装入</button>
        </div>
      </template>
      <p v-else style="color:var(--muted)">托盘已发运，禁止再装入。</p>
      <table style="margin-top:12px">
        <thead>
          <tr>
            <th>分区</th>
            <th>公斤数</th>
            <th>等级</th>
            <th v-if="!selected.shippedAt">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="l in lines" :key="l.id">
            <td>{{ l.zoneCode }}</td>
            <td>{{ Number(l.kg).toFixed(3) }}</td>
            <td><span class="badge" :class="l.grade === '甲' ? 'growing' : 'idle'">{{ l.grade }}</span></td>
            <td v-if="!selected.shippedAt" class="actions">
              <button class="btn danger" @click="removeLine(l.id)">删除</button>
            </td>
          </tr>
          <tr v-if="lines.length">
            <td><strong>合计</strong></td>
            <td><strong>{{ linesTotalKg }}</strong></td>
            <td :colspan="selected.shippedAt ? 1 : 2"></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">按温室汇总</h3>
      <table>
        <thead>
          <tr>
            <th>温室</th>
            <th>托盘数</th>
            <th>公斤汇总</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in summary" :key="s.greenhouseId">
            <td>{{ s.greenhouseName }}</td>
            <td>{{ s.palletCount }}</td>
            <td>{{ Number(s.totalKg).toFixed(3) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
