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

function renderResults (results){
    resultsEl.innerHTML = ''
    if (!results.length) {
    resultsEl.innerHTML = '<div id="empty">No results found. Try different search terms.</div>'
    return
  }
  results.forEach(r => {
    const card = document.createElement('div')
    card.className = 'result-card'
    const filename = r.source_video.split('/').pop().split('\\').pop()
    const mins = Math.floor(r.timestamp_sec/60);
    const secs = Math.floor(r.timestamp_sec%60).toString().padStart(2,'0')
    const timeLabel = `${mins}:${secs}`
    card.innerHTML = `
    <img src="file://${r.best_frame}" alt="${filename} at ${timeLabel}" />
    <div class="result-info">
        <div class="result-file">${filename}</div>
        <div class="result-time">▶ ${timeLabel}</div>
      </div>`
  card.addEventListener('click', ()=>{
    const {shell} = require('electron');
    shell.openPath(r.source_video)
  })
  resultsEl.appendChild(card)
  })
}