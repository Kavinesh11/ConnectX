// server.js
import express from 'express';
import cors from 'cors';
import fs from 'fs';
import path from 'path';
import FormData from 'form-data';
import axios from 'axios';
import dotenv from 'dotenv';

dotenv.config();

const app = express();
app.use(cors());
const PORT = 5000;

// Create downloads directory if it doesn't exist
const downloadPath = path.join('downloads');
if (!fs.existsSync(downloadPath)) {
  fs.mkdirSync(downloadPath);
}

// Function to download file from Flask server
async function downloadFileFromFlask() {
  try {
    // No initial log to reduce console output
    
    // Replace with the IP address of your Flask server
    const flaskServerUrl = 'http://192.168.25.112:5000/download';
    
    const response = await axios({
      method: 'GET',
      url: flaskServerUrl,
      responseType: 'stream'
    });
    
    // Extract filename from content-disposition header or use default
    const contentDisposition = response.headers['content-disposition'];
    const filename = contentDisposition 
      ? contentDisposition.split('filename=')[1].replace(/"/g, '')
      : 'imp.md';
      
    // Save the file
    const filePath = path.join(downloadPath, filename);
    
    return new Promise((resolve, reject) => {
      const writer = fs.createWriteStream(filePath);
      
      response.data.pipe(writer);
      
      writer.on('finish', () => {
        // No success log to reduce console output
        resolve(filePath);
      });
      
      writer.on('error', (err) => {
        console.error('Download error:', err);
        reject(err);
      });
    });
  } catch (error) {
    console.error('Download failed:', error.message);
    throw error;
  }
}

// Function to upload file to Pinata
async function uploadFileToPinata(filePath) {
  try {
    // No log about uploading to reduce console output
    
    if (!fs.existsSync(filePath)) {
      throw new Error(`${filePath} not found`);
    }

    const form = new FormData();
    form.append('file', fs.createReadStream(filePath));

    const response = await axios.post(
      'https://api.pinata.cloud/pinning/pinFileToIPFS',
      form,
      {
        maxBodyLength: 'Infinity',
        headers: {
          ...form.getHeaders(),
          pinata_api_key: process.env.PINATA_API_KEY,
          pinata_secret_api_key: process.env.PINATA_SECRET_KEY,
        },
      }
    );

    const ipfsHash = response.data.IpfsHash;
    
    // Silently delete the file after upload (no logging)
    fs.unlinkSync(filePath);

    return ipfsHash;
  } catch (err) {
    console.error('Upload failed:', err.message);
    throw err;
  }
}

// Route to manually trigger the process
app.get('/process', async (req, res) => {
  try {
    const filePath = await downloadFileFromFlask();
    const ipfsHash = await uploadFileToPinata(filePath);
    return res.json({ success: true, hash: ipfsHash });
  } catch (err) {
    console.error('Process failed:', err.message);
    return res.status(500).json({ success: false, error: err.message });
  }
});

// Auto-process on server start
async function autoProcess() {
  try {
    const filePath = await downloadFileFromFlask();
    const ipfsHash = await uploadFileToPinata(filePath);
    // No logs here to ensure hash is only printed once at the end
    return ipfsHash;
  } catch (err) {
    console.error('Process failed:', err.message);
    return null;
  }
}

// Start the server
app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
  
  // Run the auto-process when the server starts
  console.log('Starting automatic download and upload process...');
  autoProcess()
    .then(hash => {
      if (hash) {
        // Print only the hash value without any additional text
        console.log(hash);
      } else {
        console.log('Process failed');
      }
    })
    .catch(err => {
      console.error('Error in automatic process:', err);
    });
});

// Endpoint to check status and get hash
app.get('/status', (req, res) => {
  res.json({
    server: 'running',
    message: 'Server is running and auto-process was triggered on startup'
  });
});