let currentFolder = null
let dbPath = null
let framesDir =null

const folderPathEl = document.getElementById('folder-path');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
const searchInput = document.getElementById('search-input');

window.api.onStatus((msg)=>{
    statusEl.textContent = msg
})

document.getElementById('pick-btn').addEventListener('click',async ()=>{
    const folder = await window.api.pickFolder();
    if(!folder) return ;
    currentFolder = folder;
    folderPathEl.textContent = folder;
    folderPathEl.style.color = '#e0e0e0'
})

//index footage 
document.getElementById('index-btn').addEventListener('click',async ()=>{
    if(!currentFolder){
        statusEl.textContent = 'Please pick a folder first'
        return ;
    }
    statusEl.textContent = 'Starting Indexing...'
    try{
        const result = await window.api.indexFolder(currentFolder);
        dbPath = result.dbPath;
        framesDir = result.framesDir;
    }catch(err){
        statusEl.textContent = 'Error: ' + err.message
    }
})

//search footage
async function doSearch(){
const query = searchInput.value.trim();
if(!query) return 
if(!dbPath) {
    statusEl.textContent = 'Index your footage first.'
    return
  }
  statusEl.textContent = 'Searching...'
  try{
    const results = await window.api.search({query , dbPath , framesDir})
    renderResults(results)
    statusEl.textContent = `${results.length} results for "${query}"`
  }catch(err){
    statusEl.textContent = 'Error: ' + err.message
  }
}

document.getElementById('search-btn').addEventListener('click', doSearch)
searchInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch() })

function formatDuration(sec) {
  if (!sec) return 'unknown'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = Math.floor(sec % 60)
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
  return `${m}:${String(s).padStart(2,'0')}`
}

function formatTimestamp(sec) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

function renderResults (results){
    resultsEl.innerHTML = ''
    if (!results.length) {
    resultsEl.innerHTML = '<div id="empty">No results found. Try different search terms.</div>'
    return
  }
  results.forEach(r => {
    const card = document.createElement('div')
    console.log("r" , r)
    card.className = 'result-card'
    const filename = r.source_video.split('/').pop().split('\\').pop()
    const mins = Math.floor(r.timestamp_sec/60);
    const secs = Math.floor(r.timestamp_sec%60).toString().padStart(2,'0')
    const nameWithoutExt = filename.replace(/\.[^/.]+$/, '')
    console.log(mins , secs )
    const timeLabel = `${mins}:${secs}`
    card.innerHTML = `
    <div class="thumb-wrap">
        <img src="file://${r.best_frame}" alt="${filename}" />
        <span class="timestamp-badge">▶ ${formatTimestamp(r.best_timestamp)}</span>
      </div>
      <div class="result-info">
        <div class="result-file" title="${filename}">${filename}</div>
        <div class="result-meta">
          <span>${r.confidence}% match</span>
          <span>·</span>
          <span>${formatDuration(r.duration)}</span>
          <span>·</span>
          <span>${r.matching_scenes} scene${r.matching_scenes !== 1 ? 's' : ''}</span>
        </div>
        <div class="rename-row">
          <input class="rename-input" value="${nameWithoutExt}" spellcheck="false" />
          <button class="rename-btn">Rename</button>
        </div>
      </div>`
      const thumbWrap = card.querySelector('.thumb-wrap')
      thumbWrap.setAttribute('draggable', 'true')
      thumbWrap.addEventListener('dragstart', (e) => {
  // Must prevent default — Electron's startDrag takes over from here
  e.preventDefault()
  window.api.startDrag({
    videoPath:     r.source_video,
    thumbnailPath: r.best_frame
  })
})
  thumbWrap.addEventListener('click', () => {
      // const { shell } = require('electron')
      // shell.openPath(r.source_video)
      window.api.openVideo(r.source_video);
    })

    const renameBtn   = card.querySelector('.rename-btn')
    const renameInput = card.querySelector('.rename-input')
    const ext         = r.source_video.split('.').pop()
  
  // card.addEventListener('click', ()=>{
  //   const {shell} = require('electron');
  //   shell.openPath(r.source_video)
  // })
  renameBtn.addEventListener('click', async () => {
      const newName = renameInput.value.trim()
      if (!newName || newName + '.' + ext === filename) return

      renameBtn.textContent = '...'
      const result = await window.api.renameVideo({
        oldPath: r.source_video,
        newName: newName + '.' + ext
      })

      if (result.success) {
        r.source_video = result.newPath
        renameBtn.textContent = '✓'
        card.querySelector('.result-file').textContent = newName + '.' + ext
        setTimeout(() => { renameBtn.textContent = 'Rename' }, 2000)
      } else {
        renameBtn.textContent = 'Error'
        console.error(result.error)
        setTimeout(() => { renameBtn.textContent = 'Rename' }, 2000)
      }
    })

  resultsEl.appendChild(card)
  })
}