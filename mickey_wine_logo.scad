// Mickey Mouse Wine Glass Logo - Precise OpenSCAD Model
// Designed to faithfully recreate the graphic from IMG_9550.jpeg
// Suitable for 3D printing (STL export) with multi-color or pause-at-height layer swaps.

$fn = 150;

module outer_ring() {
    difference() {
        circle(r = 50);
        circle(r = 43);
    }
}

module ring_base() {
    union() {
        circle(r = 50);
        // The slight tab/bulge at the bottom right of the outer ring in the reference image
        translate([38, -38]) circle(r = 12);
    }
}

module mickey_head() {
    translate([-16, 16]) {
        // Main head circle
        circle(r = 13.5);
        // Left ear
        translate([-11.5, 11.5]) circle(r = 7.5);
        // Right ear
        translate([11.5, 11.5]) circle(r = 7.5);
    }
}

module wine_glass_contour() {
    // Glass bowl curving down and stem extending to bottom right
    union() {
        // Bowl body connected to Mickey head
        translate([-14, 10]) intersection() {
            circle(r = 16);
            translate([-20, -20]) square([40, 30]);
        }
        // Stem
        translate([-6, 2]) rotate(-45) square([3.5, 42], center=true);
        // Base foot of the wine glass
        translate([22, -22]) rotate(45) square([3, 16], center=true);
    }
}

module wine_liquid_wave() {
    // The red wine section with the characteristic wave shape in the center
    intersection() {
        translate([-16, 16]) circle(r = 13.5);
        
        // Liquid fill shape with top wave
        union() {
            translate([-30, -5]) square([40, 15]);
            // Wave crest bump in the middle
            translate([-2, 2]) circle(r = 3.5);
        }
    }
}

// ==========================================
// 3D MODEL GENERATION FOR STL EXPORT
// ==========================================

module mickey_wine_coaster_3d() {
    // 1. Black Background Disc (Base plate)
    color("Black")
    linear_extrude(height = 2.0)
        ring_base();

    // 2. Gray Outer Ring & Outlines
    color("Gray")
    translate([0, 0, 2.0])
    linear_extrude(height = 2.0)
        difference() {
            ring_base();
            offset(r = -3) ring_base();
        }

    // 3. Black Silhouette (Mickey Head & Wine Glass outline structure)
    color("Black")
    translate([0, 0, 2.0])
    linear_extrude(height = 3.5)
        union() {
            mickey_head();
            // Glass outline ring / silhouette
            difference() {
                offset(r = 1.5) wine_glass_contour();
                wine_glass_contour();
            }
        }

    // 4. Red Wine Liquid 
    color("Red")
    translate([0, 0, 3.5])
    linear_extrude(height = 1.5)
        wine_liquid_wave();
}

// Render the model
mickey_wine_coaster_3d();
