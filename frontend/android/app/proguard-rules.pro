# ---------------------------------------------------------------------------
# AgriPredict ProGuard rules
#
# The app has no reflection-based serialisation and no custom native modules,
# so the default React Native consumer rules cover most of it. These entries
# exist because a minified release build that strips them fails at runtime, not
# at build time — the worst failure mode to discover after shipping.
# ---------------------------------------------------------------------------

# Keep Hermes' annotations used by the bytecode loader.
-keep @com.facebook.proguard.annotations.DoNotStrip class *
-keepclassmembers class * {
    @com.facebook.proguard.annotations.DoNotStrip *;
}
-dontwarn com.facebook.proguard.annotations.**

# AsyncStorage bridges through native module lookup by name.
-keep class com.reactnativecommunity.asyncstorage.** { *; }

# react-native-svg resolves view managers reflectively.
-keep class com.horcrux.svg.** { *; }

# Screens/safe-area use codegen'd view manager names.
-keep class com.swmansion.rnscreens.** { *; }
-keep class com.th3rdwave.safeareacontext.** { *; }
