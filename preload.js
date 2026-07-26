const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('api', {
  pickFolder:   ()              => ipcRenderer.invoke('pick-folder'),
  indexFolder:  (folderPath)   => ipcRenderer.invoke('index-folder', folderPath),
  search:       (params)        => ipcRenderer.invoke('search', params),
  renameVideo:  (params)   => ipcRenderer.invoke('rename-video', params),
  openVideo: (videoPath) => ipcRenderer.invoke('open-video', videoPath),
  onStatus:     (callback)     => ipcRenderer.on('status', (_, msg) => callback(msg))
})