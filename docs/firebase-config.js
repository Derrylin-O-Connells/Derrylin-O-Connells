// Paste your Firebase web app config here (Firebase console > Project settings >
// Your apps > Web app > "SDK setup and configuration" > Config).
// While apiKey is empty the site runs in DEMO MODE: fixtures and results work,
// and live scoring is saved only on the device you're using.
window.FIREBASE_CONFIG = {
// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyCcSVxLEmt3lZqhvfbi-UNorrRu9XW-5BE",
  authDomain: "derrylin-gaa.firebaseapp.com",
  projectId: "derrylin-gaa",
  storageBucket: "derrylin-gaa.firebasestorage.app",
  messagingSenderId: "204495331948",
  appId: "1:204495331948:web:c27d3e611c8c6b87f06e49"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
