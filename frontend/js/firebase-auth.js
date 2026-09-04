// Firebase Auth Modular SDK Initializer
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js";
import { getAuth, signInWithPopup, GoogleAuthProvider, signOut as fbSignOut, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js";

const firebaseConfig = {
  apiKey: "AIzaSyDjds_ktHxu5AO_TRskbADWvocthdt9tqs",
  authDomain: "zero-breakout.firebaseapp.com",
  projectId: "zero-breakout",
  storageBucket: "zero-breakout.firebasestorage.app",
  messagingSenderId: "412352022079",
  appId: "1:412352022079:web:841ff398477e9dee709a8a",
  measurementId: "G-ZWMPG11LVE"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();
provider.setCustomParameters({ prompt: 'select_account' });

window.firebaseAuth = {
  auth,
  signInWithGoogle: async () => {
    const result = await signInWithPopup(auth, provider);
    return result.user;
  },
  signOut: async () => {
    await fbSignOut(auth);
  },
  onAuthStateChanged: (callback) => {
    return onAuthStateChanged(auth, callback);
  }
};
