// Standalone build: runs the Android app's JVM unit tests without the Android Gradle
// Plugin or SDK. See docs/testing.md ("Android JVM harness").
pluginManagement {
    // Use the same Kotlin version as the app (declared in the repo's root build.gradle.kts).
    val kotlinVersion = Regex("""id\("org\.jetbrains\.kotlin\.android"\)\s+version\s+"([^"]+)"""")
        .find(file("../../build.gradle.kts").readText())
        ?.groupValues?.get(1)
        ?: error("Kotlin version not found in the root build.gradle.kts")

    plugins {
        id("org.jetbrains.kotlin.jvm") version kotlinVersion
    }
    repositories {
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        // A few small AndroidX artifacts come only from Google's repository: androidx.test
        // (needed by Robolectric) and lifecycle-viewmodel with its annotations (LensViewModel).
        exclusiveContent {
            forRepository {
                google {
                    // Read plain POMs: Gradle module metadata only offers Android variants,
                    // which a JVM build cannot select. AARs are unpacked by AarClassesJar.
                    metadataSources {
                        mavenPom()
                        artifact()
                        ignoreGradleMetadataRedirection()
                    }
                }
            }
            filter {
                includeGroupByRegex("androidx\\.test.*")
                includeGroup("androidx.lifecycle")
                includeGroup("androidx.annotation")
            }
        }
        // Everything else.
        mavenCentral()
    }
}

rootProject.name = "be-my-lens-android-jvm-tests"
