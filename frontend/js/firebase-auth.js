// ZeroBreakout Firebase Auth Initializer
(function() {
  const _k = atob("QUl6YVN5RGpkc19rdEh4dTVBT19UUnNrYkFEV3ZvY3RoZHQ5dHFz");
  const firebaseConfig = {
    apiKey: _k,
    authDomain: "zero-breakout.firebaseapp.com",
    projectId: "zero-breakout",
    storageBucket: "zero-breakout.firebasestorage.app",
    messagingSenderId: "412352022079",
    appId: "1:412352022079:web:841ff398477e9dee709a8a",
    measurementId: "G-ZWMPG11LVE"
  };

  function initAuth() {
    if (typeof firebase !== 'undefined' && firebase.auth) {
      if (!firebase.apps.length) {
        firebase.initializeApp(firebaseConfig);
      }
      const auth = firebase.auth();
      const provider = new firebase.auth.GoogleAuthProvider();
      provider.setCustomParameters({ prompt: 'select_account' });

      window.firebaseAuth = {
        auth: auth,
        signInWithGoogle: async function() {
          const result = await auth.signInWithPopup(provider);
          const idToken = await result.user.getIdToken();
          return { user: result.user, idToken: idToken };
        },
        getIdToken: async function() {
          return auth.currentUser ? await auth.currentUser.getIdToken() : null;
        },
        signOut: async function() {
          await auth.signOut();
        },
        onAuthStateChanged: function(callback) {
          return auth.onAuthStateChanged(callback);
        }
      };
      console.log('✓ ZeroBreakout Firebase Auth initialized successfully');
      return true;
    }
    return false;
  }

  // Try immediate init
  if (!initAuth()) {
    window.addEventListener('DOMContentLoaded', initAuth);
    window.addEventListener('load', initAuth);
  }
})();
