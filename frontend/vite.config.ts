import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],base:'/ui/',build:{outDir:'../src/severity_service/static/ui',emptyOutDir:true,rollupOptions:{output:{manualChunks:{react:['react','react-dom'],charts:['recharts'],map:['leaflet','react-leaflet']}}}},server:{proxy:{'/v1':'http://127.0.0.1:8765','/health':'http://127.0.0.1:8765','/static':'http://127.0.0.1:8765'}}});
