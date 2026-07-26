const {app , BrowserWindow , ipcMain, dialog , shell} = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process')
const ffmpegPath = require("ffmpeg-static");
let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 600,
    webPreferences: {
        preload : path.join(__dirname , 'preload.js'),
        contextIsolation: true
    },
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#0f0f0f',
    })
    mainWindow.loadFile('index.html');
}
app.whenReady().then(createWindow);
// pick a folder 
ipcMain.handle('pick-folder',async()=>{
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory']
    })
    return result.cancelled ? null : result.filePaths[0]
})

function runPython(scriptName, args = [], onData) {
    return new Promise((resolve, reject) => {
        const pythonPath = path.join(__dirname, ".venv", "bin", "python");
        const scriptPath = path.join(__dirname, "backend", scriptName);

        const proc = spawn(
            pythonPath,
            [scriptPath, ...args],
            {
                env: {
                    ...process.env,
                    FFMPEG_PATH: ffmpegPath,
                },
            }
        );

proc.stdout.on("data", (data) => {
    const text = data.toString();

    console.log("[python stdout]", text);

    if (onData) {
        onData(text);
    }
});

        proc.stderr.on("data", (data) => {
            console.error("[python stderr]", data.toString());
        });

        proc.on("error", reject);

        proc.on("close", (code) => {
            if (code === 0) {
                resolve();
            } else {
                reject(new Error(`Python exited with code ${code}`));
            }
        });
    });
}

//Index a folder
ipcMain.handle('index-folder', async (event, folderPath) => {
  const framesDir = path.join(app.getPath('userData'), 'frames')
  const dbPath    = path.join(app.getPath('userData'), 'lancedb')
//   const ffmpegPath = process.env.FFMPEG_PATH || 'ffmpeg'
  fs.mkdirSync(framesDir, { recursive: true })

  mainWindow.webContents.send('status', 'Detecting scenes and indexing footage...')

  await runPython(
    'index_search.py',
    ['index', folderPath, dbPath, framesDir, ffmpegPath],
    (msg) => mainWindow.webContents.send('status', msg.trim())
  )

  mainWindow.webContents.send('status', 'Done! Ready to search.')
  return { framesDir, dbPath }
})
//Search
ipcMain.handle('search', async (event , {query , dbPath , framesDir})=>{
    const dbPathFull = dbPath || path.join(app.getPath('userData'),'lancedb')
    let output=''
    await runPython('index_search.py',['search',dbPathFull,query,'20'],
        (msg)=>{
            output +=msg
        }
    )
    const lines = output.trim().split('\n')
    const jsonLine = lines.findLast(l=>l.startsWith('['))
    return jsonLine ? JSON.parse(jsonLine) : []
})
ipcMain.handle('rename-video', async (event, { oldPath, newName }) => {
  const dir     = path.dirname(oldPath)
  const ext     = path.extname(oldPath)
  const newPath = path.join(dir, newName.endsWith(ext) ? newName : newName + ext)
  try {
    fs.renameSync(oldPath, newPath)
    return { success: true, newPath }
  } catch (err) {
    return { success: false, error: err.message }
  }
})
ipcMain.handle('open-video', async (_, videoPath) => {
    return shell.openPath(videoPath);
});