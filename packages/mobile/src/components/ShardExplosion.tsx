/**
 * ShardExplosion — polygon shatter effect for deleted entries.
 *
 * Usage:
 *   <ShardExplosion
 *     imageUri={uri}        // from react-native-view-shot
 *     entryWidth={width}
 *     entryHeight={height}
 *     originY={screenY}     // absolute screen Y of the entry
 *     onDone={callback}
 *   />
 *
 * Renders as a full-screen absolute overlay (pointer-events: none).
 */

import React, { useEffect, useRef } from "react";
import { Animated, Dimensions, Easing, Image, Modal, StyleSheet, View } from "react-native";

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get("window");

const COLS = 10;
const ROWS = 5;
const GRAVITY = 0.5;
const DURATION = 650;

interface Props {
  imageUri: string;
  entryWidth: number;
  entryHeight: number;
  originX: number;
  originY: number;
  onDone: () => void;
}

interface Shard {
  col: number;
  row: number;
  // velocity
  vx: number;
  vy: number;
  vr: number;
  // animated values
  translateX: Animated.Value | Animated.AnimatedInterpolation<number>;
  translateY: Animated.Value | Animated.AnimatedInterpolation<number>;
  rotate: Animated.Value | Animated.AnimatedInterpolation<string>;
  opacity: Animated.Value | Animated.AnimatedInterpolation<number>;
}

export default function ShardExplosion({
  imageUri,
  entryWidth,
  entryHeight,
  originX,
  originY,
  onDone,
}: Props) {
  const shards = useRef<Shard[]>([]);

  const sw = entryWidth / COLS;
  const sh = entryHeight / ROWS;
  const cx = entryWidth / 2;
  const cy = entryHeight / 2;

  if (shards.current.length === 0) {
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const shardCx = c * sw + sw / 2;
        const shardCy = r * sh + sh / 2;
        const dx = shardCx - cx;
        const dy = shardCy - cy;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const speed = 3 + Math.random() * 6;
        const spread = (Math.random() - 0.5) * 1.2;
        const angle = Math.atan2(dy, dx) + spread;

        const rotVal = new Animated.Value(0);
        shards.current.push({
          col: c,
          row: r,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed - Math.random() * 2,
          vr: (Math.random() - 0.5) * 360,
          translateX: new Animated.Value(0),
          translateY: new Animated.Value(0),
          rotate: rotVal.interpolate({ inputRange: [0, 1], outputRange: ["0deg", "0deg"] }),
          opacity: new Animated.Value(1),
        });
      }
    }
  }

  useEffect(() => {
    console.log("[ShardExplosion] useEffect fired, shards:", shards.current.length);
    // Simulate physics frame-by-frame and map to Animated values
    const totalFrames = Math.round((DURATION / 1000) * 60);
    const frameMs = DURATION / totalFrames;

    shards.current.forEach((s) => {
      let x = 0, y = 0, rot = 0;
      let vx = s.vx, vy = s.vy;

      // Pre-compute keyframes
      const xFrames: number[] = [0];
      const yFrames: number[] = [0];
      const rotFrames: number[] = [0];

      for (let f = 1; f <= totalFrames; f++) {
        vy += GRAVITY;
        vx *= 0.97;
        x += vx;
        y += vy;
        rot += s.vr / 60;
        xFrames.push(x);
        yFrames.push(y);
        rotFrames.push(rot);
      }

      const inputRange = Array.from({ length: totalFrames + 1 }, (_, i) => i / totalFrames);

      const progress = new Animated.Value(0);

      s.translateX = progress.interpolate({ inputRange, outputRange: xFrames });
      s.translateY = progress.interpolate({ inputRange, outputRange: yFrames });
      s.rotate = progress.interpolate({
        inputRange,
        outputRange: rotFrames.map((r) => `${r}deg`),
      }) as any;
      s.opacity = progress.interpolate({
        inputRange: [0, 0.5, 1],
        outputRange: [1, 0.7, 0],
      });

      Animated.timing(progress, {
        toValue: 1,
        duration: DURATION,
        easing: Easing.linear,
        useNativeDriver: false,
      }).start();
    });

    const timer = setTimeout(() => { console.log("[ShardExplosion] onDone called"); onDone(); }, DURATION + 50);
    return () => clearTimeout(timer);
  }, []);

  return (
    <Modal transparent visible animationType="none" statusBarTranslucent>
    <View style={[StyleSheet.absoluteFill, { zIndex: 9999 }]} pointerEvents="none">
      {shards.current.map((s, i) => {
        const left = originX + s.col * sw;
        const top = originY + s.row * sh;

        return (
          <Animated.View
            key={i}
            style={[
              styles.shard,
              {
                left,
                top,
                width: sw,
                height: sh,
                opacity: s.opacity,
                transform: [
                  { translateX: s.translateX },
                  { translateY: s.translateY },
                  { rotate: s.rotate as any },
                ],
              },
            ]}
          >
            <View style={{ width: sw, height: sh, backgroundColor: `hsl(${i * 7}, 80%, 60%)` }} />
          </Animated.View>
        );
      })}
    </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  shard: {
    position: "absolute",
    overflow: "hidden",
  },
});
